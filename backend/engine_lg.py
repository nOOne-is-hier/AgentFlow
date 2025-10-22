from __future__ import annotations
from typing import Dict, Any, List, TypedDict, Callable

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

# engine.py 에 정의된 실제 노드 구현들
from .engine import (
    Ctx,
    now_iso,
    node_parse_pdf,
    node_embed_pdf_to_chroma,  # 임베딩 + Chroma 색인
    node_merge_xlsx,
    node_validate_with_pdf,
    # export_xlsx 는 HITL 승인 후 main에서 실행하므로 LG 내부에선 건드리지 않음
)


# ---- LangGraph 상태 (체크포인트 친화: 경로/스칼라/소형 dict 위주) ----
class LGState(TypedDict, total=False):
    pdf_chunks: list  # [{page:int, text:str}, ...]
    vs_ref: str  # "chroma://"
    merged_path: str  # parquet/csv 경로
    validation_report: dict  # 검증 결과(요약)
    # artifact_id 는 LG 내에서는 만들지 않음 (HITL 승인 후 메인에서 export)


EventSink = Callable[[Dict[str, Any]], None]


def _ev(_type: str, node_id: str, message: str, detail: Dict[str, Any] | None = None):
    return {
        "type": _type,
        "nodeId": node_id,
        "message": message,
        "detail": (detail or {}),
        "ts": now_iso(),
    }


def build_langgraph(wf: Dict[str, Any], ctx: Ctx, on_event: EventSink | None = None):
    """
    Workflow(JSON) -> LangGraph.
    ⚠️ 각 노드는 'delta(변경분) dict'만 return 해야 함 (전체 state 금지).
    """
    g = StateGraph(LGState)
    node_map: Dict[str, Dict[str, Any]] = {n["id"]: n for n in wf.get("nodes", [])}
    edges: List[Dict[str, str]] = wf.get("edges", [])

    def add(nid: str):
        spec = node_map[nid]
        ntype = spec["type"]
        cfg = spec.get("config", {}) or {}

        def run(state: LGState) -> LGState:
            if on_event:
                on_event(_ev("ACTION", nid, f"{nid}({ntype}) 시작"))

            # ----- 각 노드별 실행 (delta만 리턴) -----
            if ntype == "parse_pdf":
                out = node_parse_pdf(cfg)
                pdf_chunks = out.get("pdf_chunks", [])
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "PDF 청킹 완료",
                            {
                                "chunks": len(pdf_chunks),
                                "pages": out.get("pdf_pages", 0),
                            },
                        )
                    )
                delta: LGState = {"pdf_chunks": pdf_chunks}

            elif ntype == "embed_pdf":
                # 입력은 기존 state에서 읽기만 함 (수정 금지)
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
                delta = {"vs_ref": out.get("vs_ref")}

            elif ntype == "merge_xlsx":
                out = node_merge_xlsx(cfg, {}, ctx)
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "XLSX 병합 완료",
                            {"rows": out.get("merged_rows", 0)},
                        )
                    )
                delta = {"merged_path": out.get("merged_path")}

            elif ntype == "validate_with_pdf":
                # table_in 은 경로를 넘기면 engine 쪽이 DF 로딩
                out = node_validate_with_pdf(
                    cfg, {"merge_xlsx.merged_table": state.get("merged_path")}
                )
                vr = out.get("validation_report", {})
                if on_event:
                    s = vr.get("summary", {}) if isinstance(vr, dict) else {}
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
                    # 1) 얕은 체크포인트 먼저 방출 (클라가 저장 후 대기 진입)
                    on_event(
                        _ev(
                            "OBS",
                            "hitl",
                            "STATE_CHECKPOINT",
                            {
                                "state": {
                                    "merged_path": state.get("merged_path"),
                                    "validation_report": vr,
                                }
                            },
                        )
                    )
                    # 2) 그 다음 HITL 신호
                    on_event(_ev("OBS", "hitl", "HITL_SIGNAL", {"state": "WAITING"}))
                delta = {"validation_report": vr}

            elif ntype == "export_xlsx":
                # LG 내부에선 실제 내보내기를 건너뜀 (HITL 승인 후 main에서 실행)
                if on_event:
                    on_event(
                        _ev(
                            "OBS",
                            nid,
                            "EXPORT_DEFERRED",
                            {"hint": "HITL 승인 후 서버가 export_xlsx 수행"},
                        )
                    )
                delta = {}  # 변경 없음

            else:
                raise RuntimeError(f"unsupported node: {ntype}")

            if on_event:
                keys = list(delta.keys())
                on_event(_ev("SUMMARY", nid, f"{nid} 완료", {"keys": keys}))
            return delta  # ✅ delta만 반환 (전체 state 금지)

        g.add_node(nid, run)

    # 노드/엣지 등록
    for n in wf.get("nodes", []):
        add(n["id"])
    for e in edges:
        g.add_edge(e["from"], e["to"])

    # 시작/종료 지정
    if wf.get("nodes"):
        g.set_entry_point(wf["nodes"][0]["id"])
        g.set_finish_point(wf["nodes"][-1]["id"])

    app = g.compile(checkpointer=MemorySaver())
    return app


def execute_stream_lg(wf: Dict[str, Any], ctx: Ctx):
    """
    LangGraph 실행 → 이벤트 순차 방출.
    - PLAN 선방출
    - MemorySaver가 요구하는 thread_id를 config로 지정
    """
    events: List[Dict[str, Any]] = []

    def sink(ev: Dict[str, Any]):
        events.append(ev)

    # 계획 이벤트
    sink(
        _ev(
            "PLAN",
            "plan",
            f"총 {len(wf.get('nodes', []))}개 노드 실행 계획 수립",
            {"nodes": len(wf.get("nodes", []))},
        )
    )

    app = build_langgraph(wf, ctx, on_event=sink)

    # thread_id 필수
    final_state: LGState = app.invoke(
        {}, config={"configurable": {"thread_id": ctx.run_id}}
    )  # type: ignore

    # (여기서는 추가 STATE_CHECKPOINT 불필요 — validate 시점에서 이미 방출)

    # 순서대로 방출
    for ev in events:
        yield ev
