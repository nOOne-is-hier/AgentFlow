from __future__ import annotations
from typing import Dict, Any, List, TypedDict, Callable

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .engine import (
    Ctx,
    now_iso,
    node_parse_pdf,
    node_embed_pdf_to_chroma,
    node_merge_xlsx,
    node_validate_with_pdf,
    node_export_xlsx,
)


class LGState(TypedDict, total=False):
    pdf_chunks: list
    validation_report: dict
    merged_path: str
    artifact_id: str


EventSink = Callable[[Dict[str, Any]], None]


def _ev(_type: str, node_id: str, message: str, detail: Dict[str, Any] | None = None):
    return {
        "type": _type,
        "nodeId": node_id,
        "message": message,
        "detail": detail or {},
        "ts": now_iso(),
    }


def build_langgraph(wf: Dict[str, Any], ctx: Ctx, on_event: EventSink | None = None):
    """
    Workflow(JSON) -> LangGraph 앱으로 컴파일.
    - 체크포인터: MemorySaver
    - HITL: validate 이후 승인 대기 시그널 방출
    """
    g = StateGraph(LGState)
    node_map: Dict[str, Dict[str, Any]] = {n["id"]: n for n in wf["nodes"]}
    edges: List[Dict[str, str]] = wf.get("edges", [])

    def add(nid: str):
        spec = node_map[nid]
        ntype = spec["type"]
        cfg = spec.get("config", {}) or {}

        def run(state: LGState) -> LGState:
            if on_event:
                on_event(_ev("ACTION", nid, f"{nid}({ntype}) 시작"))

            # inputs 조립
            inputs: Dict[str, Any] = {}
            if "pdf_chunks" in state:
                inputs["parse_pdf.pdf_chunks"] = state["pdf_chunks"]
            if "validation_report" in state:
                inputs["validate_with_pdf.validation_report"] = state[
                    "validation_report"
                ]
            if "merged_path" in state:
                inputs["merge_xlsx.merged_table"] = state["merged_path"]

            # 노드 실행
            if ntype == "parse_pdf":
                out = node_parse_pdf(cfg)
                state["pdf_chunks"] = out.get("pdf_chunks", [])
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "PDF 청킹 완료",
                            {"chunks": len(state["pdf_chunks"])},
                        )
                    )

            elif ntype == "embed_pdf":
                out = node_embed_pdf_to_chroma(
                    cfg, {"parse_pdf.pdf_chunks": state.get("pdf_chunks", [])}
                )
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "임베딩/색인 완료",
                            {"count": out.get("vs_count", 0)},
                        )
                    )

            elif ntype == "merge_xlsx":
                out = node_merge_xlsx(cfg, inputs, ctx)
                state["merged_path"] = out.get("merged_path")
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "XLSX 병합 완료",
                            {"rows": out.get("merged_rows", 0)},
                        )
                    )

            elif ntype == "validate_with_pdf":
                out = node_validate_with_pdf(
                    cfg,
                    {
                        "merge_xlsx.merged_table": state.get("merged_path"),
                        "parse_pdf.pdf_chunks": state.get("pdf_chunks"),
                    },
                )
                state["validation_report"] = out.get("validation_report", {})
                s = state["validation_report"].get("summary", {})
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "검증 요약",
                            {
                                "ok": s.get("ok", 0),
                                "warn": s.get("warn", 0),
                                "fail": s.get("fail", 0),
                            },
                        )
                    )
                # === HITL 인터럽트: 승인 대기 알림 ===
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            "hitl",
                            "승인 대기(HITL_WAIT)",
                            {"hint": "POST /runs/{id}/continue approve=true|false"},
                        )
                    )
                # SSE 루프가 WAITING_HITL 전이하도록 트리거
                if on_event:
                    on_event(_ev("OBS", "hitl", "HITL_SIGNAL", {"state": "WAITING"}))

            elif ntype == "export_xlsx":
                out = node_export_xlsx(
                    cfg, {"merge_xlsx.merged_table": state.get("merged_path")}, ctx
                )
                state["artifact_id"] = out.get("artifact_id")
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "산출물 경로",
                            {"artifact_id": state["artifact_id"]},
                        )
                    )

            else:
                raise RuntimeError(f"unsupported node: {ntype}")

            if on_event:
                keys = list(out.keys()) if isinstance(out, dict) else []
                on_event(_ev("SUMMARY", nid, f"{nid} 완료", {"keys": keys}))

            return state

        g.add_node(nid, run)

    # 노드/엣지 연결
    for n in wf["nodes"]:
        add(n["id"])
    for e in edges:
        g.add_edge(e["from"], e["to"])

    # 시작/종료
    if wf["nodes"]:
        g.set_entry_point(wf["nodes"][0]["id"])
        g.set_finish_point(wf["nodes"][-1]["id"])

    app = g.compile(checkpointer=MemorySaver())
    return app


def execute_stream_lg(wf: Dict[str, Any], ctx: Ctx):
    """
    1차 실행(검증까지) 후 HITL 신호를 내보내고 종료.
    - LangGraph invoke 시 반드시 thread_id를 넘긴다.
    - 이어서 재개는 외부(SSE 루프)에서 처리.
    """
    events: List[Dict[str, Any]] = []

    def sink(ev: Dict[str, Any]):
        events.append(ev)

    sink(
        _ev(
            "PLAN",
            "plan",
            f"총 {len(wf.get('nodes', []))}개 노드 실행 계획 수립",
            {"nodes": len(wf.get("nodes", []))},
        )
    )
    app = build_langgraph(wf, ctx, on_event=sink)

    # ✅ thread_id 제공 (필수)
    state = app.invoke({}, config={"configurable": {"thread_id": ctx.run_id}})

    # 수집된 이벤트를 순차 방출
    for ev in events:
        yield ev

    # 상태 체크포인트를 알림(재개용)
    yield {
        "type": "OBS",
        "nodeId": "hitl",
        "message": "STATE_CHECKPOINT",
        "detail": {"state": state},
    }
