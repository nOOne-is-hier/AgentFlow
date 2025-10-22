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
from .engine import execute_stream, Ctx, now_iso
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
        json.dump(wf.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
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
    wf = run.get("workflow")

    # LangGraph 기본 사용
    use_lg = (
        True
        if request.query_params.get("engine", "lg").lower() == "lg"
        or os.environ.get("USE_LANGGRAPH") == "1"
        else False
    )

    async def gen():
        seq = 1
        buffer_events: List[Dict[str, Any]] = []  # 어시스턴트 요약용
        validation: Dict[str, Any] | None = None
        checkpoint_state: Dict[str, Any] | None = None

        def pack(ev: Dict[str, Any]):
            nonlocal seq
            ev.setdefault("seq", seq)
            seq += 1
            buffer_events.append(ev)
            data = json.dumps(ev, ensure_ascii=False)
            return f"id: {seq}\nevent: message\ndata: {data}\n\n".encode("utf-8")

        # RUNNING 전이
        run["status"] = "RUNNING"
        _save_json(rpath, run)

        ctx = Ctx(run_id=run_id, storage=STORAGE, art_dir=ART_DIR)

        try:
            # === 1차 실행 (LG: validate까지 진행 & HITL_SIGNAL 방출) ===
            stream = execute_stream_lg(wf, ctx) if use_lg else execute_stream(wf, ctx)

            async def stream_iter():
                for ev in stream:
                    yield ev
                    await asyncio.sleep(0)

            async for ev in stream_iter():
                # HITL 신호 수신 → WAITING_HITL 전이 및 대기
                if ev.get("nodeId") == "hitl" and ev.get("message") == "HITL_SIGNAL":
                    run["status"] = "WAITING_HITL"
                    _save_json(rpath, run)
                    yield pack(
                        {
                            "type": "OBS",
                            "nodeId": "hitl",
                            "message": "WAITING_HITL",
                            "detail": {},
                        }
                    )

                    # 승인 대기 루프
                    while True:
                        await asyncio.sleep(0.6)
                        cur = _load_json(rpath, {})
                        if cur.get("status") in ("RUNNING", "CANCELLED"):
                            break

                    # 거부 시 종료
                    if _load_json(rpath, {}).get("status") == "CANCELLED":
                        yield pack(
                            {
                                "type": "SUMMARY",
                                "nodeId": "hitl",
                                "message": "사용자 거부로 취소",
                            }
                        )
                        run["status"] = "CANCELLED"
                        run["endedAt"] = now_iso()
                        _save_json(rpath, run)
                        return

                    # 승인됨
                    yield pack(
                        {
                            "type": "OBS",
                            "nodeId": "hitl",
                            "message": "APPROVED",
                            "detail": {},
                        }
                    )

                    # === 승인 후 마무리(export 실행) ===
                    # LG 체크포인트 상태에서 merged_path / export 설정 가져오기
                    if use_lg and checkpoint_state:
                        try:
                            # export 노드 spec 찾기
                            export_node = next(
                                n
                                for n in wf.get("nodes", [])
                                if n.get("type") == "export_xlsx"
                            )
                            cfg = export_node.get("config", {}) or {}
                            from .engine import node_export_xlsx  # 함수 사용

                            out = node_export_xlsx(
                                cfg,
                                {
                                    "merge_xlsx.merged_table": checkpoint_state.get(
                                        "merged_path"
                                    )
                                },
                                ctx,
                            )
                            yield pack(
                                {
                                    "type": "ACTION",
                                    "nodeId": "export",
                                    "message": "export_xlsx 시작",
                                    "detail": {},
                                }
                            )
                            yield pack(
                                {
                                    "type": "OBS",
                                    "nodeId": "export",
                                    "message": "산출물 경로",
                                    "detail": {"artifact_id": out.get("artifact_id")},
                                }
                            )
                            yield pack(
                                {
                                    "type": "SUMMARY",
                                    "nodeId": "export",
                                    "message": "export_xlsx 완료",
                                    "detail": {"keys": list(out.keys())},
                                }
                            )
                        except StopIteration:
                            # export 노드가 없으면 패스
                            pass

                elif ev.get("nodeId") == "validate" and ev.get("type") in (
                    "OBS",
                    "SUMMARY",
                ):
                    # 검증 요약 저장(어시스턴트 답장용)
                    # 자세한 report는 LG state에서 넘겨받음
                    pass

                elif (
                    ev.get("nodeId") == "hitl"
                    and ev.get("message") == "STATE_CHECKPOINT"
                ):
                    checkpoint_state = ev.get("detail", {}).get("state")

                # 이벤트 송신
                yield pack(ev)

            # === 완료 처리 ===
            run["status"] = "SUCCEEDED"
            run["endedAt"] = now_iso()

            # artifactId best-effort
            art_id = None
            for fn in os.listdir(ART_DIR):
                if fn.endswith(".xlsx") and run_id[:8] in fn:
                    art_id = fn.split(".")[0]
                    break
            run["artifactId"] = art_id
            _save_json(rpath, run)

            # 어시스턴트 답장(OpenAI Chat)
            # 검증 내용은 체크포인트 state에서 전달
            validation = (
                (checkpoint_state or {}).get("validation_report", {})
                if checkpoint_state
                else {}
            )
            reply = generate_assistant_reply(run, buffer_events, validation or {})
            yield pack(
                {
                    "type": "SUMMARY",
                    "nodeId": "assistant",
                    "message": "ASSISTANT_REPLY",
                    "detail": {"text": reply},
                }
            )

        except Exception as e:
            run["status"] = "FAILED"
            run["endedAt"] = now_iso()
            _save_json(rpath, run)
            yield pack(
                {"type": "SUMMARY", "nodeId": "runtime", "message": f"실패: {e}"}
            )

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
