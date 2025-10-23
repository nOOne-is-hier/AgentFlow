from __future__ import annotations
import os, io, json, asyncio
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from .settings import (
    APP_VERSION,
    STORAGE,
    UPLOADS,
    WF_DIR,
    RUN_DIR,
    ART_DIR,
    FILES_INDEX,
)
from .models import Workflow, GraphPatch
from .engine import execute_stream, Ctx, now_iso, node_export_xlsx
from .compact import compact_event
from .engine_lg import execute_stream_lg
from .assistant_reply import generate_assistant_reply

app = FastAPI(
    title="Agentic PoC Backend",
    version=APP_VERSION,
    openapi_tags=[
        {"name": "Auth"},
        {"name": "Files"},
        {"name": "Chat"},
        {"name": "Workflows"},
        {"name": "Runs"},
        {"name": "Artifacts"},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_json(path: str, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_dt(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


# ---------- 최신 splits/파일 선택 ----------


def _latest_splits_xlsx_paths() -> List[str]:
    base = os.path.join(STORAGE, "splits")
    if not os.path.isdir(base):
        return []
    candidates = [
        os.path.join(base, d)
        for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    ]
    latest_dir = max(candidates, key=lambda p: os.path.getmtime(p), default=None)
    if not latest_dir:
        return []
    return [
        os.path.join(latest_dir, f)
        for f in os.listdir(latest_dir)
        if f.lower().endswith(".xlsx")
    ]


def _select_latest_pdf() -> Optional[Dict[str, Any]]:
    idx = _load_json(FILES_INDEX, {"files": []})
    pdfs = [f for f in idx.get("files", []) if f.get("type") == "pdf"]
    return max(pdfs, key=lambda x: _parse_dt(x.get("uploadedAt", "")), default=None)


def _autopatch_edges(wf: dict) -> dict:
    """노드 간 필수 엣지가 빠졌을 때 PoC용으로 자동 보강."""
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    edges = list(wf.get("edges", []))

    def _has(frm, to):
        return any(e.get("from") == frm and e.get("to") == to for e in edges)

    if (
        "parse_pdf" in nodes
        and "merge_xlsx" in nodes
        and not _has("parse_pdf", "merge_xlsx")
    ):
        edges.append({"from": "parse_pdf", "to": "merge_xlsx"})
    if (
        "embed_pdf" in nodes
        and "validate" in nodes
        and not _has("embed_pdf", "validate")
    ):
        edges.append({"from": "embed_pdf", "to": "validate"})

    wf["edges"] = edges
    return wf


def _assistant_reply(run: dict, events: list[dict], validation: dict | None) -> str:
    """
    답장 스위치:
      - OPENAI_API_KEY 존재 & openai 모듈 사용 가능 → OpenAI로 요약 생성
      - 아니면 서버 내장 요약으로 fallback
    """
    import os

    # --- 공통 컨텍스트 추출(프롬프트/폴백에서 공용) ---
    run_id = run.get("runId")
    status = run.get("status")
    artifact_id = run.get("artifactId")

    # PLAN 요약
    plan_ev = next((e for e in events if e.get("type") == "PLAN"), None)
    planned_nodes = (plan_ev or {}).get("detail", {}).get("nodes")

    # 노드 완료 여부/세부 OBS 집계
    obs_by_node: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") == "OBS" and ev.get("nodeId"):
            obs_by_node.setdefault(ev["nodeId"], {})
            # 같은 키를 덮어쓰되, 마지막 OBS의 detail을 남김
            if isinstance(ev.get("detail"), dict):
                obs_by_node[ev["nodeId"]].update(ev["detail"])

    # validation summary & 샘플 evidence 3개 이내
    v_sum = {}
    v_items_sample = []
    if isinstance(validation, dict):
        v_sum = validation.get("summary", {}) or {}
        items = validation.get("items", []) or []
        # 너무 길지 않게 앞쪽 샘플 일부만 포함
        for it in items[:3]:
            v_items_sample.append(
                {
                    "policy": it.get("policy"),
                    "dept": it.get("dept"),
                    "status": it.get("status"),
                    # 증거는 페이지/짧은 스니펫만 슬라이스
                    "evidence": [
                        {
                            "page": e.get("page"),
                            "snippet": (e.get("snippet") or "")[:120],
                        }
                        for e in (it.get("evidence") or [])[:1]
                    ],
                }
            )

    # 마지막 export 관찰에서 artifact_id 보강
    if not artifact_id:
        exp_obs = next(
            (
                e
                for e in reversed(events)
                if e.get("nodeId") == "export" and e.get("type") == "OBS"
            ),
            None,
        )
        if exp_obs and isinstance(exp_obs.get("detail"), dict):
            artifact_id = exp_obs["detail"].get("artifact_id", artifact_id)

    # -------- OpenAI 경로 시도 --------
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        # 프롬프트용 컨텍스트(간결)
        context_lines = []
        context_lines.append(f"run_id: {run_id}")
        context_lines.append(f"status: {status}")
        if planned_nodes is not None:
            context_lines.append(f"planned_nodes: {planned_nodes}")
        # 핵심 OBS 요약
        pp = obs_by_node.get("parse_pdf", {})
        em = obs_by_node.get("embed_pdf", {})
        mg = obs_by_node.get("merge_xlsx", {})
        vd = obs_by_node.get("validate", {})
        context_lines.append(
            f"parse_pdf: chunks={pp.get('chunks')} pages={pp.get('pages')}"
        )
        context_lines.append(f"embed_pdf: count={em.get('count')}")
        context_lines.append(f"merge_xlsx: rows={mg.get('rows')}")
        # 검증 합계
        if v_sum:
            context_lines.append(
                f"validation_summary: ok={v_sum.get('ok',0)} warn={v_sum.get('warn',0)} fail={v_sum.get('fail',0)}"
            )
        # 샘플 evidence
        if v_items_sample:
            context_lines.append("validation_examples:")
            for it in v_items_sample:
                ev = (it.get("evidence") or [{}])[0]
                context_lines.append(
                    f"- {it.get('policy')} | dept={it.get('dept')} | status={it.get('status')} | page={ev.get('page')} | snippet={ev.get('snippet')}"
                )
        # 산출물
        if artifact_id:
            context_lines.append(f"artifact_id: {artifact_id}")

        system_msg = (
            "당신은 데이터 파이프라인 시연 어시스턴트입니다. "
            "사용자에게 '무엇을 했고(PLAN/ACTION), 어떻게 했고(근거/스니펫/페이지), 결과가 어떠한지'를 "
            "간결한 한국어로 설명하세요. 내부 추론(ToT)은 노출하지 말고 요약만 제시합니다. "
            "항상 항목형 요약(불릿)을 사용하고, 과장 없이 사실만 기술하세요. 최대 2200자."
        )
        user_msg = (
            "다음 실행 컨텍스트를 바탕으로, 시연용 응답을 작성하세요.\n"
            "요구사항:\n"
            "1) 실행 요약(실행 ID, 상태, 계획된 노드 수)\n"
            "2) 단계 요약(parse_pdf, embed_pdf, merge_xlsx, validate, export) — 각 단계 핵심 수치 포함\n"
            "3) 검증 결과 요약 및 예시 1~3건(부서/정책/페이지/스니펫)\n"
            "4) 산출물(artifact_id) 표시\n"
            "5) 공손하고 간결하게.\n"
            "\n=== 실행 컨텍스트 ===\n" + "\n".join(context_lines)
        )

        # v1 SDK 우선 → 실패 시 구버전 fallback → 그래도 실패면 내장 요약
        model = os.getenv("OPENAI_ASSIST_MODEL", "gpt-4o-mini")
        try:
            try:
                from openai import OpenAI  # v1 SDK

                client = OpenAI(api_key=key)
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                )
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return text
            except Exception:
                # 구버전 SDK 호환
                import openai  # type: ignore

                openai.api_key = key
                resp = openai.ChatCompletion.create(
                    model=model,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                )
                text = (resp.choices[0].message["content"] or "").strip()
                if text:
                    return text
        except Exception:
            # OpenAI 호출 실패 → 폴백으로 진행
            pass

    # -------- 폴백(서버 내장 요약) --------
    lines: list[str] = []
    lines.append("## 실행 요약")
    lines.append(f"- 실행 ID: {run_id}")
    lines.append(f"- 상태: {status}")
    if planned_nodes is not None:
        lines.append(f"- 계획된 노드 수: {planned_nodes}")

    # 단계 요약
    def _done(nid: str) -> bool:
        return any(
            e.get("nodeId") == nid and e.get("type") == "SUMMARY" for e in events
        )

    lines.append("")
    lines.append("### 단계 진행")
    lines.append(
        f"- parse_pdf: 완료 (chunks={obs_by_node.get('parse_pdf',{}).get('chunks')}, pages={obs_by_node.get('parse_pdf',{}).get('pages')})"
        if _done("parse_pdf")
        else "- parse_pdf: -"
    )
    lines.append(
        f"- embed_pdf: 완료 (count={obs_by_node.get('embed_pdf',{}).get('count')})"
        if _done("embed_pdf")
        else "- embed_pdf: -"
    )
    lines.append(
        f"- merge_xlsx: 완료 (rows={obs_by_node.get('merge_xlsx',{}).get('rows')})"
        if _done("merge_xlsx")
        else "- merge_xlsx: -"
    )
    if v_sum:
        lines.append(
            f"- validate: 완료 (ok={v_sum.get('ok',0)}, warn={v_sum.get('warn',0)}, fail={v_sum.get('fail',0)})"
        )
    else:
        lines.append("- validate: 완료")

    # 검증 예시
    if v_items_sample:
        lines.append("")
        lines.append("### 검증 예시")
        for it in v_items_sample:
            ev = (it.get("evidence") or [{}])[0]
            lines.append(
                f"- [{it.get('policy')}] {it.get('dept')} — {it.get('status')} (p.{ev.get('page')}) {ev.get('snippet')}"
            )

    # 산출물
    if artifact_id:
        lines.append("")
        lines.append(f"### 산출물")
        lines.append(f"- artifact_id: {artifact_id}")

    return "\n".join(lines)


# ---------- Schemas ----------
class LoginReq(BaseModel):
    email: str = "keehoon@example.com"
    empno: str = "20251234"


class LoginRes(BaseModel):
    user: Dict[str, str]


class ChatTurnReq(BaseModel):
    message: str = "부서별 xlsx 병합 후 문서 기반 검증해줘"
    fileIds: List[str] = Field(default_factory=list)


class ChatTurnRes(BaseModel):
    assistant: str
    tot: Dict[str, Any]
    graphPatch: GraphPatch


class ExecReq(BaseModel):
    workflowId: str = Field(..., examples=["wf-2025-10-22"])


class ContinueReq(BaseModel):
    approve: bool = Field(True)
    comment: Optional[str] = None


# ---------- Auth ----------
@app.post("/auth/login", response_model=LoginRes, tags=["Auth"])
def login(req: LoginReq, response: Response):
    sess = f"sess-{uuid4().hex[:12]}"
    response.set_cookie("session", sess, httponly=True)
    emp_mask = ("*" * max(0, len(req.empno) - 4)) + req.empno[-4:]
    return {"user": {"email": req.email, "empno_masked": emp_mask}}


# ---------- Files ----------
@app.post("/files/upload", tags=["Files"])
async def upload(files: List[UploadFile] = File(...)):
    idx = _load_json(FILES_INDEX, {"files": []})
    saved = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in [".pdf", ".xlsx"]:
            raise HTTPException(400, f"unsupported type: {ext}")
        fid = str(uuid4())
        outname = f"{fid}{ext}"
        dest = os.path.join(UPLOADS, outname)
        with open(dest, "wb") as w:
            w.write(await f.read())
        meta = {
            "id": fid,
            "name": f.filename,
            "type": "pdf" if ext == ".pdf" else "xlsx",
            "size": os.path.getsize(dest),
            "path": dest,
            "uploadedAt": now_iso(),
        }
        idx["files"].append(meta)
        saved.append(meta)
    _save_json(FILES_INDEX, idx)
    return {"files": saved}


@app.get("/files", tags=["Files"])
def list_files():
    return _load_json(FILES_INDEX, {"files": []})


# ---------- Chat ----------
def _build_nodes_and_edges(pdf: Dict[str, Any], xlsx_paths: List[str]):
    nodes = [
        {
            "id": "parse_pdf",
            "type": "parse_pdf",
            "label": "PDF 파싱",
            "config": {"pdf_path": pdf["path"], "chunk_size": 1200, "overlap": 200},
            "in": [],
            "out": ["pdf_chunks"],
        },
        {
            "id": "embed_pdf",
            "type": "embed_pdf",
            "label": "PDF 임베딩(Chroma)",
            "config": {"chunks_in": "parse_pdf.pdf_chunks", "reset": True},
            "in": ["parse_pdf.pdf_chunks"],
            "out": ["vs_ref"],
        },
        {
            "id": "merge_xlsx",
            "type": "merge_xlsx",
            "label": "XLSX 병합",
            "config": {
                "xlsx_paths": xlsx_paths,
                "flatten": True,
                "split": "by_department",
            },
            "in": [],
            "out": ["merged_table"],
        },
        {
            "id": "validate",
            "type": "validate_with_pdf",
            "label": "검증(exists/sum_check)",
            "config": {"table_in": "merge_xlsx.merged_table", "tolerance": 0.005},
            "in": ["merge_xlsx.merged_table"],
            "out": ["validation_report"],
        },
        {
            "id": "export",
            "type": "export_xlsx",
            "label": "XLSX 내보내기",
            "config": {
                "table_in": "merge_xlsx.merged_table",
                "filename": "2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx",
            },
            "in": ["merge_xlsx.merged_table"],
            "out": ["artifact_path"],
        },
    ]
    edges = [
        {"from": "parse_pdf", "to": "embed_pdf"},
        {"from": "merge_xlsx", "to": "validate"},
        {"from": "validate", "to": "export"},
    ]
    return nodes, edges


@app.post("/chat/turn", response_model=ChatTurnRes, tags=["Chat"])
def chat_turn(req: ChatTurnReq = Body(...)):
    idx = _load_json(FILES_INDEX, {"files": []})
    idmap = {f["id"]: f for f in idx.get("files", [])}
    pdf = (
        next(
            (idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"] == "pdf"),
            None,
        )
        or _select_latest_pdf()
    )
    if not pdf:
        raise HTTPException(
            400, "PDF가 필요합니다. /files/upload 로 PDF 업로드 후 다시 시도하세요."
        )

    xlsx_paths = [
        idmap[i]["path"]
        for i in req.fileIds
        if i in idmap and idmap[i]["type"] == "xlsx"
    ]
    if not xlsx_paths:
        xlsx_paths = _latest_splits_xlsx_paths()
    if not xlsx_paths:
        raise HTTPException(
            400,
            "XLSX가 필요합니다. 업로드하거나 storage/splits/<최신>에 XLSX를 배치하세요.",
        )

    nodes, edges = _build_nodes_and_edges(pdf, xlsx_paths)
    patch = {"addNodes": nodes, "addEdges": edges}
    return {
        "assistant": "요청을 이해했습니다. 부서별 병합 후 문서 기반 검증을 수행하고 결과 XLSX를 생성합니다.",
        "tot": {"steps": ["쿼리 이해", "계획 수립", "그래프 작성"]},
        "graphPatch": patch,
    }


# ---------- Workflows ----------
@app.get("/workflows", tags=["Workflows"])
def wf_list():
    files = []
    for name in os.listdir(WF_DIR):
        if name.endswith(".json"):
            with open(os.path.join(WF_DIR, name), "r", encoding="utf-8") as f:
                files.append(json.load(f))
    return files


@app.post("/workflows", tags=["Workflows"])
def wf_save(wf: Workflow):
    path = os.path.join(WF_DIR, f"{wf.id}.json")
    with open(path, "w", encoding="utf-8") as f:
        # Use mode='json' to properly serialize datetime objects
        json.dump(
            wf.model_dump(by_alias=True, mode="json"), f, ensure_ascii=False, indent=2
        )
    return {"id": wf.id}


@app.get("/workflows/{wf_id}", tags=["Workflows"])
def wf_get(wf_id: str):
    path = os.path.join(WF_DIR, f"{wf_id}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "workflow not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/workflows/quickstart", tags=["Workflows"])
def wf_quickstart():
    pdf = _select_latest_pdf()
    xlsx_paths = _latest_splits_xlsx_paths()
    if not (pdf and xlsx_paths):
        raise HTTPException(400, "최신 PDF 또는 splits XLSX를 찾을 수 없습니다.")
    nodes, edges = _build_nodes_and_edges(pdf, xlsx_paths)
    wf = {
        "id": f"wf-{uuid4().hex[:8]}",
        "name": "Budget-Validation",
        "nodes": nodes,
        "edges": edges,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    _save_json(os.path.join(WF_DIR, f"{wf['id']}.json"), wf)
    return {"id": wf["id"], "nodes": len(nodes), "edges": len(edges)}


# ---------- Runs ----------
@app.post("/pipeline/execute", tags=["Runs"])
def execute(req: ExecReq):
    wpath = os.path.join(WF_DIR, f"{req.workflowId}.json")
    if not os.path.exists(wpath):
        raise HTTPException(404, "workflow not found")
    with open(wpath, "r", encoding="utf-8") as f:
        wf = json.load(f)
    run_id = str(uuid4())
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    run = {
        "runId": run_id,
        "status": "PLANNING",
        "workflow": wf,
        "startedAt": now_iso(),
        "endedAt": None,
        "artifactId": None,
        "checkpoint": None,
    }
    _save_json(rpath, run)
    return {"runId": run_id}


@app.get("/runs/{run_id}", tags=["Runs"])
def run_status(run_id: str):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    return _load_json(rpath, {})


@app.post("/runs/{run_id}/continue", tags=["Runs"])
def run_continue(run_id: str, body: ContinueReq):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    run = _load_json(rpath, {})
    if run.get("status") == "WAITING_HITL":
        run["status"] = "RUNNING" if body.approve else "CANCELLED"
        _save_json(rpath, run)
    return {"status": run.get("status")}


# ---------- SSE: 실행 + HITL 대기 + 재개 + 어시스턴트 답장 ----------
@app.get("/runs/{run_id}/events", tags=["Runs"])
async def run_events(run_id: str, request: Request):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    run = _load_json(rpath, {})
    wf = run.get("workflow") or {}
    wf = _autopatch_edges(wf)

    use_lg = (
        True
        if request.query_params.get("engine", "lg").lower() == "lg"
        or os.environ.get("USE_LANGGRAPH") == "1"
        else False
    )

    async def gen():
        seq = 1
        buffer_events: List[Dict[str, Any]] = []
        checkpoint_state: Dict[str, Any] | None = None
        stream_active = True

        def send(ev: Dict[str, Any], has_more: bool = True):
            nonlocal seq
            ev.setdefault("seq", seq)
            seq += 1
            ev["has_more"] = has_more
            cev = compact_event(ev)
            buffer_events.append(cev)
            data = json.dumps(cev, ensure_ascii=False)
            return f"id: {seq}\nevent: message\ndata: {data}\n\n".encode("utf-8")

        run["status"] = "RUNNING"
        _save_json(rpath, run)

        ctx = Ctx(run_id=run_id, storage=STORAGE, art_dir=ART_DIR)

        try:
            stream = execute_stream_lg(wf, ctx) if use_lg else execute_stream(wf, ctx)

            async def stream_iter():
                for ev in stream:
                    yield ev
                    await asyncio.sleep(0.8)

            async for ev in stream_iter():
                if ev.get("nodeId") == "hitl" and ev.get("message") == "HITL_SIGNAL":
                    run["status"] = "WAITING_HITL"
                    _save_json(rpath, run)
                    yield send(
                        {
                            "type": "OBS",
                            "nodeId": "hitl",
                            "message": "WAITING_HITL",
                            "detail": {},
                        },
                        has_more=True,
                    )
                    while True:
                        await asyncio.sleep(0.5)
                        cur = _load_json(rpath, {})
                        if cur.get("status") in ("RUNNING", "CANCELLED"):
                            break
                    if _load_json(rpath, {}).get("status") == "CANCELLED":
                        yield send(
                            {
                                "type": "SUMMARY",
                                "nodeId": "hitl",
                                "message": "사용자 거부로 취소",
                                "detail": {},
                            },
                            has_more=False,
                        )
                        run["status"] = "CANCELLED"
                        run["endedAt"] = now_iso()
                        _save_json(rpath, run)
                        stream_active = False
                        return
                    export_node = next(
                        (
                            n
                            for n in wf.get("nodes", [])
                            if n.get("type") == "export_xlsx"
                        ),
                        None,
                    )
                    if export_node:
                        yield send(
                            {
                                "type": "ACTION",
                                "nodeId": "export",
                                "message": "export_xlsx 시작",
                                "detail": {},
                            },
                            has_more=True,
                        )
                        out = node_export_xlsx(
                            export_node.get("config", {}),
                            {
                                "merge_xlsx.merged_table": (checkpoint_state or {}).get(
                                    "merged_path"
                                )
                            },
                            ctx,
                        )
                        yield send(
                            {
                                "type": "OBS",
                                "nodeId": "export",
                                "message": "산출물 생성",
                                "detail": {"artifact_id": out.get("artifact_id")},
                            },
                            has_more=True,
                        )
                        yield send(
                            {
                                "type": "SUMMARY",
                                "nodeId": "export",
                                "message": "export_xlsx 완료",
                                "detail": {"keys": list(out.keys())},
                            },
                            has_more=True,
                        )
                    continue

                if (
                    ev.get("nodeId") == "hitl"
                    and ev.get("message") == "STATE_CHECKPOINT"
                ):
                    checkpoint_state = ev.get("detail", {}).get("state")

                yield send(ev, has_more=True)

            run["status"] = "SUCCEEDED"
            run["endedAt"] = now_iso()
            art_id = None
            for fn in os.listdir(ART_DIR):
                if fn.endswith(".xlsx") and run_id[:8] in fn:
                    art_id = fn.split(".")[0]
                    break
            run["artifactId"] = art_id
            _save_json(rpath, run)

            reply = _assistant_reply(
                run, buffer_events, (checkpoint_state or {}).get("validation_report")
            )
            yield send(
                {
                    "type": "SUMMARY",
                    "nodeId": "assistant",
                    "message": "ASSISTANT_REPLY",
                    "detail": {"text": reply},
                },
                has_more=False,
            )
            stream_active = False

        except Exception as e:
            run["status"] = "FAILED"
            run["endedAt"] = now_iso()
            _save_json(rpath, run)
            yield send(
                {
                    "type": "SUMMARY",
                    "nodeId": "runtime",
                    "message": f"실패: {e}",
                    "detail": {},
                },
                has_more=False,
            )
            stream_active = False

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), headers=headers)


# ---------- Artifacts ----------
@app.get("/artifacts/{artifact_id}", tags=["Artifacts"])
def get_artifact(artifact_id: str):
    xlsx_path = os.path.join(ART_DIR, f"{artifact_id}.xlsx")
    if not os.path.exists(xlsx_path):
        raise HTTPException(404, "artifact not found")
    display_name = f"{artifact_id}.xlsx"
    meta_path = os.path.join(ART_DIR, f"{artifact_id}.meta.json")
    if os.path.exists(meta_path):
        try:
            dn = _load_json(meta_path, {}).get("display_name")
            if isinstance(dn, str) and dn.strip():
                display_name = dn
        except Exception:
            pass
    return FileResponse(
        xlsx_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=display_name,
    )
