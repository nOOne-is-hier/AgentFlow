#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_DIR="backend"
mkdir -p "$BACKEND_DIR"
: > "$BACKEND_DIR/__init__.py"

# --- requirements update (adds numpy, pypdf) ---
if ! grep -q '^numpy' "$BACKEND_DIR/requirements.txt" 2>/dev/null; then
  cat >> "$BACKEND_DIR/requirements.txt" << 'EOF'
numpy==2.1.2
pypdf==5.0.1
EOF
fi

# --- engine.py: minimal real node implementations ---
cat > "$BACKEND_DIR/engine.py" << 'EOF'
from __future__ import annotations
import os, re, json, math, io
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np
from pypdf import PdfReader
import pandas as pd

KST = timezone.utc  # simplify; display handled by client

def now_iso():
    return datetime.now(KST).isoformat()

@dataclass
class Ctx:
    run_id: str
    storage: str
    art_dir: str

# ----------------- Helpers -----------------

def _tok(text: str) -> List[str]:
    # naive tokenization for ko/en
    text = re.sub(r"[\t\r\f]+", " ", text)
    text = re.sub(r"[\-–—\.,:;!?()\[\]{}<>\'\"]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [t for t in text.split(" ") if t]

def _hash_embed(tokens: List[str], dim: int = 512) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    for t in tokens:
        idx = (hash(t) % dim)
        v[idx] += 1.0
    # l2 normalize
    n = np.linalg.norm(v)
    if n > 0:
        v = v / n
    return v

# ----------------- Nodes -----------------

def node_parse_pdf(cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = cfg["pdf_path"]
    chunk_size = int(cfg.get("chunk_size", 1200))
    overlap = int(cfg.get("overlap", 200))
    reader = PdfReader(path)
    chunks: List[Dict[str, Any]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"\s+", " ", text)
        # sliding window
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            snippet = text[start:end]
            chunks.append({"page": i, "text": snippet})
            if end == len(text):
                break
            start = max(0, end - overlap)
    return {"pdf_chunks": chunks}


def node_embed_pdf(cfg: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    # inputs expects parse_pdf.pdf_chunks
    key = cfg.get("chunks_in", "parse_pdf.pdf_chunks")
    chunks = _dig(inputs, key)
    vecs: List[np.ndarray] = []
    for ch in chunks:
        toks = _tok(ch.get("text", ""))
        vecs.append(_hash_embed(toks))
    arr = np.stack(vecs) if vecs else np.zeros((0,512), dtype=np.float32)
    return {"pdf_embeddings": {"shape": arr.shape, "data": arr.tolist(), "pages": [c.get("page",1) for c in chunks], "texts": [c.get("text","") for c in chunks]}}


def node_build_vectorstore(cfg: Dict[str, Any], inputs: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    emb = _dig(inputs, cfg.get("embeddings_in", "embed_pdf.pdf_embeddings"))
    arr = np.array(emb["data"], dtype=np.float32)
    pages = emb.get("pages", [])
    texts = emb.get("texts", [])
    os.makedirs(os.path.join(ctx.storage, "vs"), exist_ok=True)
    rid = f"vs-{ctx.run_id[:8]}"
    path = os.path.join(ctx.storage, "vs", f"{rid}.npz")
    np.savez_compressed(path, data=arr, pages=np.array(pages), texts=np.array(texts, dtype=object))
    return {"vs_ref": path}


def node_merge_xlsx(cfg: Dict[str, Any]) -> Dict[str, Any]:
    xlsx_path = cfg["xlsx_path"]
    flatten = bool(cfg.get("flatten", True))
    # read all sheets
    all_sheets = pd.read_excel(xlsx_path, sheet_name=None)
    frames: List[pd.DataFrame] = []
    for name, df in all_sheets.items():
        df = df.copy()
        df["__sheet__"] = name
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if flatten:
        merged.columns = [str(c).strip() for c in merged.columns]
    return {"merged_table": merged}


def _auto_detect_columns(df: pd.DataFrame) -> Tuple[str, str]:
    # heuristics for department and amount column names
    cand_dept = [c for c in df.columns if any(k in str(c) for k in ["부서", "부문", "팀", "과", "기관", "부서명"]) ]
    dept_col = cand_dept[0] if cand_dept else df.columns[0]
    num_cols = [c for c in df.columns if df[c].dtype.kind in "fi" or re.search(r"(금액|합계|총액|세출|지출)", str(c))]
    amt_col = num_cols[0] if num_cols else df.columns[-1]
    return dept_col, amt_col


def _numbers_in_text(s: str) -> List[int]:
    nums = re.findall(r"\d{1,3}(?:,\d{3})*|\d+", s)
    out = []
    for n in nums:
        try:
            out.append(int(n.replace(",", "")))
        except Exception:
            pass
    return out


def node_validate_with_pdf(cfg: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    # table_in: merge_xlsx.merged_table, vs_in (optional), tolerance
    table = _dig(inputs, cfg.get("table_in", "merge_xlsx.merged_table"))
    chunks = _dig(inputs, "parse_pdf.pdf_chunks")  # for evidence
    tol = float(cfg.get("tolerance", 0.005))
    if isinstance(table, pd.DataFrame):
        df = table.copy()
    else:
        # best-effort conversion
        df = pd.DataFrame(table)
    if df.empty:
        return {
            "validation_report": {
                "summary": {"ok":0, "warn":0, "fail":1},
                "items": [ {"policy":"exists","dept":"*","status":"miss","evidence":[]} ]
            }
        }

    dept_col, amt_col = _auto_detect_columns(df)
    items = []
    ok = warn = fail = 0

    # simple per-dept aggregation
    grouped = df.groupby(dept_col)[amt_col].sum(numeric_only=True)

    # index chunks by page
    by_page: Dict[int, List[Dict[str,Any]]] = {}
    for ch in chunks:
        by_page.setdefault(int(ch.get("page",1)), []).append(ch)

    for dept, expected in grouped.items():
        dept_str = str(dept)
        # exists: find any chunk containing dept string
        evid: List[Dict[str,Any]] = []
        pages_hit = []
        for ch in chunks:
            if dept_str and dept_str in ch.get("text",""):
                pages_hit.append(int(ch.get("page",1)))
                evid.append({"page": int(ch.get("page",1)), "snippet": ch.get("text","")[:180]})
                break
        if evid:
            items.append({"policy":"exists", "dept": dept_str, "status":"ok", "evidence": evid})
            ok += 1
        else:
            items.append({"policy":"exists", "dept": dept_str, "status":"miss", "evidence": []})
            fail += 1

        # sum_check: look into numbers on the same page if exists
        found = None
        if evid:
            p = evid[0]["page"]
            texts = [c.get("text","") for c in by_page.get(p, [])]
            nums = []
            for t in texts:
                nums.extend(_numbers_in_text(t))
            # heuristic: pick the closest number to expected by relative error
            if nums:
                nums_sorted = sorted(nums, key=lambda x: abs((x - expected) / (expected + 1e-9)))
                found = nums_sorted[0]
        if found is None:
            # fallback: not enough evidence
            items.append({"policy":"sum_check", "dept": dept_str, "status":"diff", "expected": int(expected), "found": 0, "delta": int(expected)})
            warn += 1
        else:
            delta = int(found) - int(expected)
            status = "ok" if (abs(delta) <= max(1, int(expected * tol))) else "diff"
            if status == "ok":
                ok += 1
            else:
                warn += 1
            items.append({"policy":"sum_check", "dept": dept_str, "status": status, "expected": int(expected), "found": int(found), "delta": int(delta), "evidence": evid})

    summary = {"ok": int(ok), "warn": int(warn), "fail": int(fail)}
    return {"validation_report": {"summary": summary, "items": items}}


def node_export_xlsx(cfg: Dict[str, Any], inputs: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    table = _dig(inputs, cfg.get("table_in", "merge_xlsx.merged_table"))
    report = _dig(inputs, "validate_with_pdf.validation_report")
    name = cfg.get("filename", "validation_result.xlsx")
    os.makedirs(ctx.art_dir, exist_ok=True)
    # artifact id & path
    art_id = f"art-{ctx.run_id[:8]}"
    path = os.path.join(ctx.art_dir, f"{art_id}.xlsx")

    with pd.ExcelWriter(path) as w:
        if isinstance(table, pd.DataFrame):
            table.to_excel(w, index=False, sheet_name="merged")
        else:
            pd.DataFrame(table).to_excel(w, index=False, sheet_name="merged")
        # validation sheet
        if report:
            # summary
            summ = report.get("summary", {})
            pd.DataFrame([summ]).to_excel(w, index=False, sheet_name="summary")
            # items
            items = report.get("items", [])
            pd.DataFrame(items).to_excel(w, index=False, sheet_name="items")
    return {"artifact_path": path, "artifact_id": art_id}

# ----------------- Executor -----------------

NODE_IMPLS = {
    "parse_pdf": node_parse_pdf,
    "embed_pdf": node_embed_pdf,
    "build_vectorstore": node_build_vectorstore,
    "merge_xlsx": node_merge_xlsx,
    "validate_with_pdf": node_validate_with_pdf,
    "export_xlsx": node_export_xlsx,
}


def _dig(obj: Dict[str, Any], dotted: str):
    # supports a.b style lookup in inputs map
    if "." not in dotted:
        return obj.get(dotted)
    parts = dotted.split('.')
    cur = obj
    for i, p in enumerate(parts):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            # also allow top-level registry by "nodeId.output"
            cur = obj.get("%s.%s" % (parts[0], parts[1]), None) if i==0 and len(parts)>=2 else None
    return cur


def execute_stream(workflow: Dict[str, Any], ctx: Ctx):
    # generator of SSE-friendly events while executing nodes sequentially
    outputs: Dict[str, Any] = {}

    def ev(_type: str, node_id: str, message: str, detail: Dict[str,Any]=None):
        return {"type": _type, "nodeId": node_id, "message": message, "detail": detail or {}, "ts": now_iso()}

    yield ev("PLAN", "plan", f"총 {len(workflow.get('nodes', []))}개 노드 실행 계획 수립", {"nodes": len(workflow.get('nodes', []))})

    for node in workflow.get("nodes", []):
        nid = node["id"]
        ntype = node["type"]
        cfg = node.get("config", {})
        yield ev("ACTION", nid, f"{nid}({ntype}) 시작")
        impl = NODE_IMPLS.get(ntype)
        try:
            if not impl:
                raise RuntimeError(f"no impl for {ntype}")
            if ntype in ("embed_pdf", "validate_with_pdf"):
                out = impl(cfg, {**outputs})
            elif ntype in ("build_vectorstore", "export_xlsx"):
                out = impl(cfg, {**outputs}, ctx)
            else:
                out = impl(cfg)
            # store outputs under both short key and namespaced key
            for k, v in out.items():
                outputs[k] = v
                outputs[f"{nid}.{k}"] = v
            yield ev("SUMMARY", nid, f"{nid} 완료", {"keys": list(out.keys())})
        except Exception as e:
            yield ev("SUMMARY", nid, f"{nid} 실패: {e.__class__.__name__}: {e}")
            raise

    # finalize
    art = outputs.get("artifact_path") or outputs.get("export.artifact_path")
    art_id = outputs.get("artifact_id") or outputs.get("export.artifact_id")
    yield ev("SUMMARY", "export", "산출물 생성", {"artifactId": art_id, "path": art})

EOF

# --- app.py patch to use engine for real execution in SSE ---
cat > "$BACKEND_DIR/app.py" << 'EOF'
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
    {"name": "Auth"}, {"name": "Files"}, {"name": "Chat"},
    {"name": "Workflows"}, {"name": "Runs"}, {"name": "Artifacts"}
]

app = FastAPI(title="Agentic PoC Backend", version="0.3", openapi_tags=TAGS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
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
            "type": "pdf" if ext==".pdf" else "xlsx",
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


def _build_nodes_and_edges(pdf: Dict[str,Any], xls: Dict[str,Any]):
    nodes = [
        {"id":"parse_pdf","type":"parse_pdf","label":"PDF 파싱","config":{"pdf_path":pdf["path"],"chunk_size":1200,"overlap":200},"in":[],"out":["pdf_chunks"]},
        {"id":"embed_pdf","type":"embed_pdf","label":"PDF 임베딩","config":{"chunks_in":"parse_pdf.pdf_chunks","model":"hash512"},"in":["parse_pdf.pdf_chunks"],"out":["pdf_embeddings"]},
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

# ---------- Chat ----------
@app.post("/chat/turn", response_model=ChatTurnRes, tags=["Chat"])
def chat_turn(req: ChatTurnReq):
    idx = _load_json(FILES_INDEX, {"files": []})
    idmap = {f["id"]: f for f in idx.get("files", [])}
    pdf = next((idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"]=="pdf"), None)
    xls = next((idmap[i] for i in req.fileIds if i in idmap and idmap[i]["type"]=="xlsx"), None)
    if not (pdf and xls):
        pdf_auto, xls_auto = _select_latest_pdf_xlsx()
        pdf = pdf or pdf_auto
        xls = xls or xls_auto
    if not (pdf and xls):
        raise HTTPException(400, "PDF/XLSX가 필요합니다. /files/upload 먼저 실행")

    nodes, edges = _build_nodes_and_edges(pdf, xls)
    patch = {"addNodes": nodes, "addEdges": edges}
    return {
        "assistant": "최신 업로드 파일을 기준으로 검증 그래프를 구성했습니다.",
        "tot": {"steps": ["쿼리 이해", "계획 수립", "그래프 작성"]},
        "graphPatch": patch,
    }

# ---------- Workflows ----------
@app.get("/workflows", tags=["Workflows"])
def wf_list():
    files = []
    for name in os.listdir(WF_DIR):
        if name.endswith('.json'):
            with open(os.path.join(WF_DIR, name), 'r', encoding='utf-8') as f:
                files.append(json.load(f))
    return files

@app.post("/workflows", tags=["Workflows"])
def wf_save(wf: Workflow):
    path = os.path.join(WF_DIR, f"{wf.id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(wf.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
    return {"id": wf.id}

@app.get("/workflows/{wf_id}", tags=["Workflows"])
def wf_get(wf_id: str):
    path = os.path.join(WF_DIR, f"{wf_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="workflow not found")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.post("/workflows/quickstart", tags=["Workflows"])
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

# ---------- Runs ----------
@app.post("/pipeline/execute", tags=["Runs"]) 
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
        def pack(ev: Dict[str,Any]):
            nonlocal seq
            ev.setdefault("seq", seq); seq += 1
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
                if run_id[:8] in fn and fn.endswith('.xlsx'):
                    run["artifactId"] = fn.split('.')[0]
                    break
            _save_json(rpath, run)
        except Exception as e:
            run["status"] = "FAILED"; run["endedAt"] = now_iso()
            _save_json(rpath, run)
            yield pack({"type":"SUMMARY","nodeId":"runtime","message": f"실패: {e}"})

    headers = {"Content-Type":"text/event-stream","Cache-Control":"no-cache","Connection":"keep-alive"}
    return StreamingResponse(gen(), headers=headers)

# ---------- Artifacts ----------
@app.get("/artifacts/{artifact_id}", tags=["Artifacts"]) 
def get_artifact(artifact_id: str):
    path = os.path.join(ART_DIR, f"{artifact_id}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"{artifact_id}.xlsx")
EOF

printf "[OK] Engine added and app wired for real execution over SSE.\n"
