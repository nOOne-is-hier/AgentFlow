#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Patch v1: Swagger defaults, auto-file selection, quickstart endpoint
# Assumes repo created by bootstrap_poc.sh

BACKEND_DIR="backend"

# Ensure package init (namespace ok, but create for clarity)
mkdir -p "$BACKEND_DIR"
: > "$BACKEND_DIR/__init__.py"

cat > "$BACKEND_DIR/app.py" << 'EOF'
from __future__ import annotations
import os, io, json, shutil, asyncio
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from .models import (
    Workflow, GraphPatch, RunEvent,
)

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

# ---------------- OpenAPI tags ----------------
TAGS = [
    {"name": "Auth", "description": "로그인(더미) 및 세션 쿠키 발급"},
    {"name": "Files", "description": "PDF/XLSX 업로드 및 열람"},
    {"name": "Chat", "description": "자연어 → 그래프 패치(GraphPatch) 생성"},
    {"name": "Workflows", "description": "워크플로우 저장/조회 및 빠른 생성(Quickstart)"},
    {"name": "Runs", "description": "파이프라인 실행/상태/SSE 이벤트"},
    {"name": "Artifacts", "description": "산출물(XLSX) 다운로드"},
]

app = FastAPI(
    title="Agentic PoC Backend",
    version="0.2",
    openapi_tags=TAGS,
    description=(
        "SPEC-Driven / YAGNI PoC. Swagger의 예제값과 기본값을 제공하여 "
        "문서만 보고 엔드투엔드 테스트가 가능하도록 구성했습니다."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---------------- Helpers ----------------
FILES_INDEX = os.path.join(STORAGE, "files.index.json")

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

# 선택 보조: 최신 PDF/XLSX 자동 선택

def _parse_dt(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except Exception:
        return 0.0

def _select_latest_pdf_xlsx() -> Tuple[Optional[Dict[str,Any]], Optional[Dict[str,Any]]]:
    idx = _load_json(FILES_INDEX, {"files": []})
    files = idx.get("files", [])
    pdfs = [f for f in files if f.get("type") == "pdf"]
    xlss = [f for f in files if f.get("type") == "xlsx"]
    pdf = max(pdfs, key=lambda x: _parse_dt(x.get("uploadedAt","")), default=None)
    xls = max(xlss, key=lambda x: _parse_dt(x.get("uploadedAt","")), default=None)
    return pdf, xls

# 노드/엣지 빌더(한 곳에서 재사용)

def _build_nodes_and_edges(pdf: Dict[str,Any], xls: Dict[str,Any]):
    nodes = [
        {"id":"parse_pdf","type":"parse_pdf","label":"PDF 파싱","config":{"pdf_path":pdf["path"],"chunk_size":1200,"overlap":200},"in":[],"out":["pdf_chunks"]},
        {"id":"embed_pdf","type":"embed_pdf","label":"PDF 임베딩","config":{"chunks_in":"parse_pdf.pdf_chunks","model":"text-embedding-3-small"},"in":["parse_pdf.pdf_chunks"],"out":["pdf_embeddings"]},
        {"id":"build_vs","type":"build_vectorstore","label":"VectorStore","config":{"embeddings_in":"embed_pdf.pdf_embeddings","collection":"budget_pdf"},"in":["embed_pdf.pdf_embeddings"],"out":["vs_ref"]},
        {"id":"merge_xlsx","type":"merge_xlsx","label":"XLSX 병합","config":{"xlsx_path":xls["path"],"flatten":True,"split":"by_department"},"in":[],"out":["merged_table"]},
        {"id":"validate","type":"validate_with_pdf","label":"검증","config":{"table_in":"merge_xlsx.merged_table","vs_in":"build_vs.vs_ref","policies":["exists","sum_check"],"tolerance":0.005},"in":["merge_xlsx.merged_table","build_vs.vs_ref"],"out":["validation_report"]},
        {"id":"export","type":"export_xlsx","label":"XLSX 내보내기","config":{"table_in":"merge_xlsx.merged_table","filename":"검증결과.xlsx"},"in":["merge_xlsx.merged_table"],"out":["artifact_path"]}
    ]
    edges = [
        {"from":"parse_pdf","to":"embed_pdf"},
        {"from":"embed_pdf","to":"build_vs"},
        {"from":"merge_xlsx","to":"validate"},
        {"from":"build_vs","to":"validate"},
        {"from":"validate","to":"export"}
    ]
    return nodes, edges

# ---------------- Schemas w/ examples ----------------
class LoginReq(BaseModel):
    email: str = "keehoon@example.com"
    empno: str = "20251234"
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "email": "keehoon@example.com",
                "empno": "20251234"
            }]
        }
    }

class LoginRes(BaseModel):
    user: Dict[str, str]

class ChatTurnReq(BaseModel):
    message: str = "부서별 집계 검증 파이프라인 만들어줘"
    fileIds: List[str] = Field(default_factory=list, description="비워두면 최신 PDF, XLSX 자동 선택")
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "부서별 세출 합계 문서 기준으로 맞는지 확인해줘", "fileIds": []},
                {"message": "exists/sum_check로 검증 그래프 생성", "fileIds": ["<pdf-id>", "<xlsx-id>"]}
            ]
        }
    }

class ChatTurnRes(BaseModel):
    assistant: str
    tot: Dict[str, Any]
    graphPatch: GraphPatch

class ExecReq(BaseModel):
    workflowId: str = Field(..., examples=["wf-2025-10-22"])

class ContinueReq(BaseModel):
    approve: bool = Field(True, examples=[True])
    comment: Optional[str] = Field(None, examples=["합계 확인, 진행 승인"])

# ---------------- Auth ----------------
@app.post("/auth/login", response_model=LoginRes, tags=["Auth"], summary="더미 로그인")
def login(req: LoginReq, response: Response):
    sess = f"sess-{uuid4().hex[:12]}"
    response.set_cookie("session", sess, httponly=True)
    emp_mask = ("*" * max(0, len(req.empno) - 4)) + req.empno[-4:]
    return {"user": {"email": req.email, "empno_masked": emp_mask}}

# ---------------- Files ----------------
@app.post("/files/upload", tags=["Files"], summary="PDF/XLSX 업로드")
async def upload(files: List[UploadFile] = File(..., description="PDF·XLSX 여러 개 업로드")):
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

@app.get("/files", tags=["Files"], summary="업로드 목록")
def list_files():
    return _load_json(FILES_INDEX, {"files": []})

# ---------------- Chat → GraphPatch ----------------
@app.post("/chat/turn", response_model=ChatTurnRes, tags=["Chat"], summary="자연어 → 그래프 패치", description="fileIds가 비어있으면 최신 PDF/XLSX 자동 선택")
def chat_turn(req: ChatTurnReq):
    # 우선 fileIds로 시도
    idx = _load_json(FILES_INDEX, {"files": []})
    idmap = {f["id"]: f for f in idx.get("files", [])}
    pdf = next((idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"]=="pdf"), None)
    xls = next((idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"]=="xlsx"), None)

    # 없으면 최신 파일 자동 선택
    if not (pdf and xls):
        pdf_auto, xls_auto = _select_latest_pdf_xlsx()
        pdf = pdf or pdf_auto
        xls = xls or xls_auto

    if not (pdf and xls):
        raise HTTPException(status_code=400, detail="PDF/XLSX가 필요합니다. 먼저 /files/upload로 업로드하세요.")

    nodes, edges = _build_nodes_and_edges(pdf, xls)
    patch = {"addNodes": nodes, "addEdges": edges}

    return {
        "assistant": "요청을 이해했습니다. 최신 업로드 파일을 기준으로 검증 그래프를 구성했습니다.",
        "tot": {"steps": ["쿼리 이해", "계획 수립", "그래프 작성"]},
        "graphPatch": patch,
    }

# ---------------- Workflows ----------------
@app.get("/workflows", tags=["Workflows"], summary="워크플로우 목록")
def wf_list():
    files = []
    for name in os.listdir(WF_DIR):
        if name.endswith('.json'):
            with open(os.path.join(WF_DIR, name), 'r', encoding='utf-8') as f:
                files.append(json.load(f))
    return files

@app.post("/workflows", tags=["Workflows"], summary="워크플로우 저장")
def wf_save(wf: Workflow):
    path = os.path.join(WF_DIR, f"{wf.id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(wf.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
    return {"id": wf.id}

@app.get("/workflows/{wf_id}", tags=["Workflows"], summary="워크플로우 조회")
def wf_get(wf_id: str):
    path = os.path.join(WF_DIR, f"{wf_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="workflow not found")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.post("/workflows/quickstart", tags=["Workflows"], summary="최신 PDF+XLSX로 워크플로우 자동 생성/저장")
def wf_quickstart():
    pdf, xls = _select_latest_pdf_xlsx()
    if not (pdf and xls):
        raise HTTPException(400, "최신 PDF/XLSX를 찾을 수 없습니다. /files/upload 먼저 실행")
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

# ---------------- Runs & Execute ----------------
@app.post("/pipeline/execute", tags=["Runs"], summary="파이프라인 실행(run 생성)")
def execute(req: ExecReq):
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

@app.get("/runs/{run_id}", tags=["Runs"], summary="실행 상태 조회")
def run_status(run_id: str):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    return _load_json(rpath, {})

@app.post("/runs/{run_id}/continue", tags=["Runs"], summary="HITL 승인/보류")
def run_continue(run_id: str, body: ContinueReq):
    rpath = os.path.join(RUN_DIR, f"{run_id}.json")
    if not os.path.exists(rpath):
        raise HTTPException(404, "run not found")
    run = _load_json(rpath, {})
    if run.get("status") == "WAITING_HITL":
        run["status"] = "RUNNING" if body.approve else "CANCELLED"
        _save_json(rpath, run)
    return {"status": run.get("status")}

# ---------------- SSE ----------------
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
        df = pd.DataFrame({"메시지":["PoC 생성물"],"생성시각":[now_iso()]})
        with pd.ExcelWriter(art_path) as writer:
            df.to_excel(writer, index=False, sheet_name="개요")
    except Exception:
        with open(art_path, 'wb') as f:
            f.write(b'')

    yield _ev({"type":"ACTION","nodeId":"export","message":"XLSX 산출물을 생성합니다.","detail":{"artifactId":art_id}})
    await asyncio.sleep(0.1)
    yield _ev({"type":"SUMMARY","nodeId":"export","message":"XLSX 생성 완료.","detail":{"artifactId":art_id}})

    run["status"] = "SUCCEEDED"
    run["endedAt"] = now_iso()
    run["artifactId"] = art_id
    _save_json(rpath, run)

@app.get("/runs/{run_id}/events", tags=["Runs"], summary="SSE 이벤트 구독")
async def run_events(run_id: str):
    headers = {"Content-Type":"text/event-stream","Cache-Control":"no-cache","Connection":"keep-alive"}
    return StreamingResponse(_simulate_events(run_id), headers=headers)

# ---------------- Artifacts ----------------
@app.get("/artifacts/{artifact_id}", tags=["Artifacts"], summary="XLSX 다운로드")
def get_artifact(artifact_id: str):
    path = os.path.join(ART_DIR, f"{artifact_id}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"{artifact_id}.xlsx")
EOF

printf "[OK] Patched backend/app.py with Swagger defaults + auto selection + quickstart.\n"
