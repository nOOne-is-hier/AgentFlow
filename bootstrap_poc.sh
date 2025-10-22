#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Agentic-PoC bootstrap (backend-first)
# Root: run this in /c/Users/lasni/Desktop/agent
# It creates a minimal FastAPI backend that matches the SPEC v0.1
# (auth/files/chat/workflows/execute/SSE/artifacts). YAGNI 적용.
# ============================================================

ROOT_DIR=$(pwd)
BACKEND_DIR="backend"
STORAGE_DIR="storage"

mkdir -p "$BACKEND_DIR" "$STORAGE_DIR" \
  "$STORAGE_DIR/uploads" "$STORAGE_DIR/workflows" \
  "$STORAGE_DIR/runs" "$STORAGE_DIR/artifacts"

# ---------- backend/requirements.txt ----------
cat > "$BACKEND_DIR/requirements.txt" << 'EOF'
fastapi==0.115.5
uvicorn[standard]==0.32.0
pydantic==2.9.2
python-multipart==0.0.17
aiofiles==24.1.0
pandas==2.2.3
openpyxl==3.1.5
EOF

# ---------- backend/models.py (from SPEC types) ----------
cat > "$BACKEND_DIR/models.py" << 'EOF'
from typing import List, Literal, Optional, Union, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

# AwareDatetime 대용: Pydantic v2에서 timezone-aware로 직렬화
class AwareDatetime(datetime):
    @classmethod
    def now_kst(cls):
        # Asia/Seoul 고정(간단화). 운영에서는 zoneinfo 사용 권장.
        return datetime.now(timezone.utc).astimezone()

NodeType = Literal[
    "parse_pdf", "embed_pdf", "build_vectorstore",
    "merge_xlsx", "validate_with_pdf", "export_xlsx"
]

OutKey = Literal[
    "pdf_chunks", "pdf_embeddings", "vs_ref",
    "merged_table", "validation_report", "artifact_path"
]

class Edge(BaseModel):
    from_: str = Field(alias="from")
    to: str

class BaseNode(BaseModel):
    id: str
    type: NodeType
    label: str
    config: Dict[str, Any]
    in_: List[str] = Field(alias="in")
    out: List[OutKey]

class Workflow(BaseModel):
    id: str
    name: str
    nodes: List[BaseNode]
    edges: List[Edge]
    createdAt: datetime
    updatedAt: datetime

class GraphPatch(BaseModel):
    addNodes: Optional[List[BaseNode]] = None
    addEdges: Optional[List[Edge]] = None
    updateLabels: Optional[List[Dict[str, str]]] = None
    removeNodes: Optional[List[str]] = None
    removeEdges: Optional[List[Edge]] = None

# ---- Validation Report ----
class Evidence(BaseModel):
    page: int = Field(ge=1)
    snippet: str = Field(min_length=5, max_length=600)

class ExistsItem(BaseModel):
    policy: Literal["exists"]
    dept: str
    status: Literal["ok", "miss"]
    evidence: Optional[List[Evidence]] = None

class SumCheckItem(BaseModel):
    policy: Literal["sum_check"]
    dept: str
    status: Literal["ok", "diff"]
    expected: int
    found: int
    delta: Optional[int] = None
    evidence: Optional[List[Evidence]] = None

class ValidationSummary(BaseModel):
    ok: int
    warn: int
    fail: int

class ValidationReport(BaseModel):
    summary: ValidationSummary
    items: List[Union[ExistsItem, SumCheckItem]]

# ---- Run Event (SSE) ----
class RunEvent(BaseModel):
    seq: int = Field(ge=1)
    ts: datetime
    type: Literal["PLAN", "ACTION", "OBS", "SUMMARY"]
    message: str
    nodeId: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
EOF

# ---------- backend/app.py ----------
cat > "$BACKEND_DIR/app.py" << 'EOF'
from __future__ import annotations
import os, io, json, shutil, asyncio
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from .models import (
    Workflow, GraphPatch, RunEvent,
)

APP_TZ = timezone.utc  # 간단화 (표시는 클라이언트가 처리)
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

app = FastAPI(title="Agentic PoC Backend", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ------------------ Helpers ------------------

def now_iso() -> str:
    return datetime.now(APP_TZ).isoformat()

def _save_json(path: str, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

FILES_INDEX = os.path.join(STORAGE, "files.index.json")

# ------------------ Schemas ------------------
class LoginReq(BaseModel):
    email: str
    empno: str

class LoginRes(BaseModel):
    user: Dict[str, str]

class ChatTurnReq(BaseModel):
    message: str
    fileIds: List[str]

class ChatTurnRes(BaseModel):
    assistant: str
    tot: Dict[str, Any]
    graphPatch: GraphPatch

class ExecReq(BaseModel):
    workflowId: str

class ContinueReq(BaseModel):
    approve: bool
    comment: Optional[str] = None

# ------------------ Auth ------------------
@app.post("/auth/login", response_model=LoginRes)
def login(req: LoginReq, response: Response):
    sess = f"sess-{uuid4().hex[:12]}"
    response.set_cookie("session", sess, httponly=True)
    emp_mask = ("*" * max(0, len(req.empno) - 4)) + req.empno[-4:]
    return {"user": {"email": req.email, "empno_masked": emp_mask}}

# ------------------ Files ------------------
@app.post("/files/upload")
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
            "type": "pdf" if ext==".pdf" else "xlsx",
            "size": os.path.getsize(dest),
            "path": dest,
            "uploadedAt": now_iso(),
        }
        idx["files"].append(meta)
        saved.append(meta)
    _save_json(FILES_INDEX, idx)
    return {"files": saved}

@app.get("/files")
def list_files():
    return _load_json(FILES_INDEX, {"files": []})

# ------------------ Chat Turn (build GraphPatch) ------------------
@app.post("/chat/turn", response_model=ChatTurnRes)
def chat_turn(req: ChatTurnReq):
    idx = _load_json(FILES_INDEX, {"files": []})
    idmap = {f["id"]: f for f in idx.get("files", [])}
    pdf = next((idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"]=="pdf"), None)
    xls = next((idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"]=="xlsx"), None)

    if not (pdf and xls):
        raise HTTPException(status_code=400, detail="need one PDF and one XLSX in fileIds")

    nodes = [
        {"id":"parse_pdf","type":"parse_pdf","label":"PDF 파싱","config":{"pdf_path":pdf["path"],"chunk_size":1200,"overlap":200},"in":[],"out":["pdf_chunks"]},
        {"id":"embed_pdf","type":"embed_pdf","label":"PDF 임베딩","config":{"chunks_in":"parse_pdf.pdf_chunks","model":"text-embedding-3-small"},"in":["parse_pdf.pdf_chunks"],"out":["pdf_embeddings"]},
        {"id":"build_vs","type":"build_vectorstore","label":"VectorStore","config":{"embeddings_in":"embed_pdf.pdf_embeddings","collection":"budget_pdf"},"in":["embed_pdf.pdf_embeddings"],"out":["vs_ref"]},
        {"id":"merge_xlsx","type":"merge_xlsx","label":"XLSX 병합","config":{"xlsx_path":xls["path"],"flatten":True,"split":"by_department"},"in":[],"out":["merged_table"]},
        {"id":"validate","type":"validate_with_pdf","label":"검증","config":{"table_in":"merge_xlsx.merged_table","vs_in":"build_vs.vs_ref","policies":["exists","sum_check"],"tolerance":0.005},"in":["merge_xlsx.merged_table","build_vs.vs_ref"],"out":["validation_report"]},
        {"id":"export","type":"export_xlsx","label":"XLSX 내보내기","config":{"table_in":"merge_xlsx.merged_table","filename":"2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx"},"in":["merge_xlsx.merged_table"],"out":["artifact_path"]}
    ]
    patch = {"addNodes": nodes, "addEdges": [
        {"from":"parse_pdf","to":"embed_pdf"},
        {"from":"embed_pdf","to":"build_vs"},
        {"from":"merge_xlsx","to":"validate"},
        {"from":"build_vs","to":"validate"},
        {"from":"validate","to":"export"}
    ]}

    return {
        "assistant": "요청을 이해했습니다. 부서별 집계 후 문서 기준으로 검증하겠습니다.",
        "tot": {"steps": ["쿼리 이해", "계획 수립", "그래프 작성"]},
        "graphPatch": patch,
    }

# ------------------ Workflows ------------------
@app.get("/workflows")
def wf_list():
    files = []
    for name in os.listdir(WF_DIR):
        if name.endswith('.json'):
            with open(os.path.join(WF_DIR, name), 'r', encoding='utf-8') as f:
                files.append(json.load(f))
    return files

@app.post("/workflows")
def wf_save(wf: Workflow):
    path = os.path.join(WF_DIR, f"{wf.id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(wf.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
    return {"id": wf.id}

@app.get("/workflows/{wf_id}")
def wf_get(wf_id: str):
    path = os.path.join(WF_DIR, f"{wf_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="workflow not found")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# ------------------ Runs & Execute ------------------
STATUS = {"PLANNING","WAITING_HITL","RUNNING","SUCCEEDED","FAILED","CANCELLED"}

@app.post("/pipeline/execute")
def execute(req: ExecReq):
    # Snapshot workflow
    wpath = os.path.join(WF_DIR, f"{req.workflowId}.json")
    if not os.path.exists(wpath):
        raise HTTPException(404, "workflow not found")
    with open(wpath, 'r', encoding='utf-8') as f:
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

@app.get("/runs/{run_id}")
def run_status(run_id: str):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    return _load_json(rpath, {})

@app.post("/runs/{run_id}/continue")
def run_continue(run_id: str, body: ContinueReq):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    run = _load_json(rpath, {})
    if run.get("status") == "WAITING_HITL":
        run["status"] = "RUNNING" if body.approve else "CANCELLED"
        _save_json(rpath, run)
    return {"status": run.get("status")}

# --------------- SSE (events) ---------------

async def _simulate_events(run_id: str):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    run = _load_json(rpath, None)
    if not run:
        yield b"\n"  # noop
        return
    wf = run["workflow"]

    seq = 1
    def _ev(ev: Dict[str, Any]):
        nonlocal seq
        ev.setdefault("seq", seq)
        ev.setdefault("ts", now_iso())
        seq += 1
        data = json.dumps(ev, ensure_ascii=False)
        return f"id: {ev['seq']}\nevent: message\ndata: {data}\n\n".encode("utf-8")

    # PLAN
    yield _ev({"type":"PLAN","nodeId":"plan","message":"사용자 요청을 쿼리 이해 에이전트로 전달합니다.","detail":{}})
    await asyncio.sleep(0.2)
    yield _ev({"type":"SUMMARY","nodeId":"plan","message":f"파이프라인 초안({len(wf['nodes'])}노드) 생성 완료.","detail":{"nodes":len(wf['nodes'])}})

    # switch RUNNING
    run["status"] = "RUNNING"
    _save_json(rpath, run)

    # ACTION/SUMMARY per node
    for node in wf["nodes"]:
        yield _ev({"type":"ACTION","nodeId":node["id"],"message":f"{node['id']} 실행을 시작합니다.","detail":{}})
        await asyncio.sleep(0.2)
        if node["id"] == "validate":
            yield _ev({"type":"OBS","nodeId":"validate","message":"exists 0/0 ok, sum_check 0/0 ok (stub)","detail":{"ok":0,"diff":0}})
        yield _ev({"type":"SUMMARY","nodeId":node["id"],"message":f"{node['id']} 완료","detail":{}})
        await asyncio.sleep(0.1)

    # artifact (stub xlsx)
    art_id = f"art-{uuid4().hex[:6]}"
    art_path = os.path.join(ART_DIR, f"{art_id}.xlsx")
    try:
        import pandas as pd
        from openpyxl import Workbook
        df = pd.DataFrame({"메시지":["PoC 생성물"],"생성시각":[now_iso()]})
        with pd.ExcelWriter(art_path) as writer:
            df.to_excel(writer, index=False, sheet_name="개요")
    except Exception as e:
        # fallback 빈 파일
        with open(art_path, 'wb') as f:
            f.write(b'')

    yield _ev({"type":"ACTION","nodeId":"export","message":"XLSX 산출물을 생성합니다.","detail":{"artifactId":art_id}})
    await asyncio.sleep(0.1)
    yield _ev({"type":"SUMMARY","nodeId":"export","message":"XLSX 생성 완료.","detail":{"artifactId":art_id}})

    run["status"] = "SUCCEEDED"
    run["endedAt"] = now_iso()
    run["artifactId"] = art_id
    _save_json(rpath, run)

@app.get("/runs/{run_id}/events")
async def run_events(run_id: str):
    headers = {"Content-Type":"text/event-stream","Cache-Control":"no-cache","Connection":"keep-alive"}
    return StreamingResponse(_simulate_events(run_id), headers=headers)

# --------------- Artifacts ---------------
@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    path = os.path.join(ART_DIR, f"{artifact_id}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"{artifact_id}.xlsx")

EOF

# ---------- runner scripts ----------
cat > run_backend.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Prefer uv if available
if command -v uv >/dev/null 2>&1; then
  uv venv -p 3.11 || true
  uv pip install -r backend/requirements.txt
  uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
else
  python -m venv .venv || true
  source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
  pip install -U pip
  pip install -r backend/requirements.txt
  uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
fi
EOF
chmod +x run_backend.sh

# ---------- .env.sample ----------
cat > .env.sample << 'EOF'
OPENAI_API_KEY=
EOF

# ---------- done ----------
echo "[OK] Backend PoC files written. Next steps:"
echo "1) (선택) cp .env.sample .env && 편집"
echo "2) ./run_backend.sh"
echo "3) 브라우저에서 http://localhost:8000/docs 열기"
