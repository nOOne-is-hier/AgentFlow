from __future__ import annotations
import os, io, json, asyncio
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from .models import Workflow, GraphPatch
from .engine import execute_stream, Ctx, now_iso

APP_TZ = timezone.utc
ROOT = os.path.abspath(os.getcwd())
STORAGE = os.path.join(ROOT, "storage")
UPLOADS = os.path.join(STORAGE, "uploads")
WF_DIR = os.path.join(STORAGE, "workflows")
RUN_DIR = os.path.join(STORAGE, "runs")
ART_DIR = os.path.join(STORAGE, "artifacts")

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(WF_DIR, exist_ok=True)
os.makedirs(RUN_DIR, exist_ok=True)
os.makedirs(ART_DIR, exist_ok=True)

TAGS = [
    {"name": "Auth"},
    {"name": "Files"},
    {"name": "Chat"},
    {"name": "Workflows"},
    {"name": "Runs"},
    {"name": "Artifacts"},
]

app = FastAPI(title="Agentic PoC Backend", version="0.3", openapi_tags=TAGS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FILES_INDEX = os.path.join(STORAGE, "files.index.json")


def _save_json(path: str, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 상단 유틸 근처에 추가
def _latest_split_dir() -> Optional[str]:
    base = os.path.join(STORAGE, "splits")
    if not os.path.isdir(base):
        return None
    # 하위 폴더 중 수정시각 최신 선택
    candidates = [
        os.path.join(base, d)
        for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _all_xlsx_in(dirpath: str) -> List[str]:
    out = []
    for fn in os.listdir(dirpath):
        if fn.lower().endswith(".xlsx"):
            out.append(os.path.join(dirpath, fn))
    return out


# ---------- Schemas with examples ----------
class LoginReq(BaseModel):
    email: str = "keehoon@example.com"
    empno: str = "20251234"


class LoginRes(BaseModel):
    user: Dict[str, str]


class ChatTurnReq(BaseModel):
    message: str = "부서별 집계 검증 파이프라인 만들어줘"
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
            raise HTTPException(status_code=400, detail=f"unsupported type: {ext}")
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


# ---------- Helpers for chat ----------
from typing import Tuple


def _parse_dt(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _select_latest_pdf_xlsx() -> (
    Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]
):
    idx = _load_json(FILES_INDEX, {"files": []})
    files = idx.get("files", [])
    pdfs = [f for f in files if f.get("type") == "pdf"]
    xlss = [f for f in files if f.get("type") == "xlsx"]
    pdf = max(pdfs, key=lambda x: _parse_dt(x.get("uploadedAt", "")), default=None)
    xls = max(xlss, key=lambda x: _parse_dt(x.get("uploadedAt", "")), default=None)
    return pdf, xls


# 기존: _build_nodes_and_edges(pdf, xls) -> 다중 XLSX로 확장
def _build_nodes_and_edges(pdf: Dict[str, Any], xls_or_paths: Any):
    # xls_or_paths: 단일 파일(meta) or 경로 리스트
    if isinstance(xls_or_paths, list):
        xlsx_paths = xls_or_paths
    else:
        xlsx_paths = [xls_or_paths["path"]]

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
            "label": "PDF 임베딩",
            "config": {"chunks_in": "parse_pdf.pdf_chunks", "model": "hash512"},
            "in": ["parse_pdf.pdf_chunks"],
            "out": ["pdf_embeddings"],
        },
        {
            "id": "build_vs",
            "type": "build_vectorstore",
            "label": "VectorStore",
            "config": {
                "embeddings_in": "embed_pdf.pdf_embeddings",
                "collection": "budget_pdf",
            },
            "in": ["embed_pdf.pdf_embeddings"],
            "out": ["vs_ref"],
        },
        # 👇 핵심: 여러 XLSX 병합
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
            "label": "검증",
            "config": {
                "table_in": "merge_xlsx.merged_table",
                "vs_in": "build_vs.vs_ref",
                "policies": ["exists", "sum_check"],
                "tolerance": 0.005,
            },
            "in": ["merge_xlsx.merged_table", "build_vs.vs_ref"],
            "out": ["validation_report"],
        },
        # 👇 파일명 고정
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
        {"from": "embed_pdf", "to": "build_vs"},
        {"from": "merge_xlsx", "to": "validate"},
        {"from": "build_vs", "to": "validate"},
        {"from": "validate", "to": "export"},
    ]
    return nodes, edges


# ---------- Chat ----------
# /chat/turn: 채팅 삽입 파일에서 '모든 XLSX'를 수집, 없으면 splits 최신 폴더 자동 탐색
@app.post("/chat/turn", response_model=ChatTurnRes, tags=["Chat"])
def chat_turn(req: ChatTurnReq):
    idx = _load_json(FILES_INDEX, {"files": []})
    idmap = {f["id"]: f for f in idx.get("files", [])}

    # 명시 파일
    pdf = next(
        (idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"] == "pdf"),
        None,
    )
    xls_list = [
        idmap[i]["path"]
        for i in req.fileIds
        if i in idmap and idmap[i]["type"] == "xlsx"
    ]

    # 보강: 최신 업로드 자동
    if not pdf:
        pdf_auto, _ = _select_latest_pdf_xlsx()
        pdf = pdf_auto

    # 추가 보강: splits 최신 디렉터리 전체 수집
    if not xls_list:
        sdir = _latest_split_dir()
        if sdir:
            xls_list = _all_xlsx_in(sdir)

    if not (pdf and xls_list):
        raise HTTPException(
            400,
            "PDF와 XLSX(여러 개)가 필요합니다. /files/upload 또는 storage/splits 준비 확인",
        )

    nodes, edges = _build_nodes_and_edges(pdf, xls_list)
    patch = {"addNodes": nodes, "addEdges": edges}
    return {
        "assistant": f"PDF 1개, XLSX {len(xls_list)}개로 검증 그래프를 구성했습니다.",
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
        raise HTTPException(status_code=404, detail="workflow not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/workflows/quickstart", tags=["Workflows"])
def wf_quickstart():
    pdf, xls = _select_latest_pdf_xlsx()
    if not (pdf and xls):
        raise HTTPException(
            400, "최신 PDF/XLSX를 찾을 수 없습니다. /files/upload 먼저 실행"
        )
    nodes, edges = _build_nodes_and_edges(pdf, xls)
    wf = {
        "id": f"wf-{uuid4().hex[:8]}",
        "name": "Budget-Validation",
        "nodes": nodes,
        "edges": edges,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    path = os.path.join(WF_DIR, f"{wf['id']}.json")
    _save_json(path, wf)
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


# ---------- SSE executes real workflow on connect ----------
@app.get("/runs/{run_id}/events", tags=["Runs"])
async def run_events(run_id: str):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    run = _load_json(rpath, {})
    wf = run.get("workflow")

    async def gen():
        seq = 1

        def pack(ev: Dict[str, Any]):
            nonlocal seq
            ev.setdefault("seq", seq)
            seq += 1
            data = json.dumps(ev, ensure_ascii=False)
            return f"id: {seq}\nevent: message\ndata: {data}\n\n".encode("utf-8")

        # switch to RUNNING now
        run["status"] = "RUNNING"
        _save_json(rpath, run)

        ctx = Ctx(run_id=run_id, storage=STORAGE, art_dir=ART_DIR)
        try:
            for ev in execute_stream(wf, ctx):
                yield pack(ev)
                await asyncio.sleep(0)  # cooperative

            # finalize
            run["status"] = "SUCCEEDED"
            # artifact id will be inside last event detail; re-scan artifact dir quick
            run["endedAt"] = now_iso()
            # (best-effort) try to find artifact
            for fn in os.listdir(ART_DIR):
                if run_id[:8] in fn and fn.endswith(".xlsx"):
                    run["artifactId"] = fn.split(".")[0]
                    break
            _save_json(rpath, run)
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
# /artifacts/{artifact_id}: 메타의 표시 이름으로 다운로드 파일명 설정
@app.get("/artifacts/{artifact_id}", tags=["Artifacts"])
def get_artifact(artifact_id: str):
    xlsx_path = os.path.join(ART_DIR, f"{artifact_id}.xlsx")
    if not os.path.exists(xlsx_path):
        raise HTTPException(status_code=404, detail="artifact not found")
    display_name = f"{artifact_id}.xlsx"
    meta_path = os.path.join(ART_DIR, f"{artifact_id}.meta.json")
    if os.path.exists(meta_path):
        try:
            meta = _load_json(meta_path, {})
            dn = meta.get("display_name")
            if isinstance(dn, str) and dn.strip():
                display_name = dn
        except Exception:
            pass
    return FileResponse(
        xlsx_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=display_name,
    )
