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
        idx = hash(t) % dim
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
    arr = np.stack(vecs) if vecs else np.zeros((0, 512), dtype=np.float32)
    return {
        "pdf_embeddings": {
            "shape": arr.shape,
            "data": arr.tolist(),
            "pages": [c.get("page", 1) for c in chunks],
            "texts": [c.get("text", "") for c in chunks],
        }
    }


def node_build_vectorstore(
    cfg: Dict[str, Any], inputs: Dict[str, Any], ctx: Ctx
) -> Dict[str, Any]:
    emb = _dig(inputs, cfg.get("embeddings_in", "embed_pdf.pdf_embeddings"))
    arr = np.array(emb["data"], dtype=np.float32)
    pages = emb.get("pages", [])
    texts = emb.get("texts", [])
    os.makedirs(os.path.join(ctx.storage, "vs"), exist_ok=True)
    rid = f"vs-{ctx.run_id[:8]}"
    path = os.path.join(ctx.storage, "vs", f"{rid}.npz")
    np.savez_compressed(
        path, data=arr, pages=np.array(pages), texts=np.array(texts, dtype=object)
    )
    return {"vs_ref": path}


def node_merge_xlsx(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    병합 규칙:
      - cfg.xlsx_paths: string[] 이면 모든 파일을 concat
      - 아니면 cfg.xlsx_path: string 단일 파일과 호환
    """

    def read_one(xp: str) -> List[pd.DataFrame]:
        if not xp or not os.path.exists(xp):
            raise FileNotFoundError(xp)
        all_sheets = pd.read_excel(xp, sheet_name=None)
        out = []
        for name, df in all_sheets.items():
            df = df.copy()
            df["__sheet__"] = name
            df["__file__"] = os.path.basename(xp)
            out.append(df)
        return out

    flatten = bool(cfg.get("flatten", True))
    paths = cfg.get("xlsx_paths")
    frames: List[pd.DataFrame] = []

    if paths and isinstance(paths, list) and len(paths) > 0:
        for xp in paths:
            frames.extend(read_one(xp))
    else:
        xlsx_path = cfg.get("xlsx_path")
        if not xlsx_path:
            raise FileNotFoundError("xlsx_paths 또는 xlsx_path 미지정")
        frames.extend(read_one(xlsx_path))

    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if flatten:
        merged.columns = [str(c).strip() for c in merged.columns]
    return {"merged_table": merged}


def _auto_detect_columns(df: pd.DataFrame) -> Tuple[str, str]:
    # heuristics for department and amount column names
    cand_dept = [
        c
        for c in df.columns
        if any(k in str(c) for k in ["부서", "부문", "팀", "과", "기관", "부서명"])
    ]
    dept_col = cand_dept[0] if cand_dept else df.columns[0]
    num_cols = [
        c
        for c in df.columns
        if df[c].dtype.kind in "fi" or re.search(r"(금액|합계|총액|세출|지출)", str(c))
    ]
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


def node_validate_with_pdf(
    cfg: Dict[str, Any], inputs: Dict[str, Any]
) -> Dict[str, Any]:
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
                "summary": {"ok": 0, "warn": 0, "fail": 1},
                "items": [
                    {"policy": "exists", "dept": "*", "status": "miss", "evidence": []}
                ],
            }
        }

    dept_col, amt_col = _auto_detect_columns(df)
    items = []
    ok = warn = fail = 0

    # simple per-dept aggregation
    s = df[amt_col].astype(str).str.strip()

    s = s.str.replace(r"^\\((\\1))$", r"-\\g<1>", regex=True)  # (1,234) -> -1,234

    s = s.str.replace(",", "", regex=False)

    s = s.str.replace(r"[^0-9\.\-]", "", regex=True)

    df["_amt_"] = pd.to_numeric(s, errors="coerce")

    grouped = df.groupby(dept_col)["_amt_"].sum()

    # index chunks by page
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for ch in chunks:
        by_page.setdefault(int(ch.get("page", 1)), []).append(ch)

    for dept, expected in grouped.items():
        dept_str = str(dept)
        # exists: find any chunk containing dept string
        evid: List[Dict[str, Any]] = []
        pages_hit = []
        for ch in chunks:
            if dept_str and dept_str in ch.get("text", ""):
                pages_hit.append(int(ch.get("page", 1)))
                evid.append(
                    {
                        "page": int(ch.get("page", 1)),
                        "snippet": ch.get("text", "")[:180],
                    }
                )
                break
        if evid:
            items.append(
                {"policy": "exists", "dept": dept_str, "status": "ok", "evidence": evid}
            )
            ok += 1
        else:
            items.append(
                {"policy": "exists", "dept": dept_str, "status": "miss", "evidence": []}
            )
            fail += 1

        # sum_check: look into numbers on the same page if exists
        found = None
        if evid:
            p = evid[0]["page"]
            texts = [c.get("text", "") for c in by_page.get(p, [])]
            nums = []
            for t in texts:
                nums.extend(_numbers_in_text(t))
            # heuristic: pick the closest number to expected by relative error
            if nums:
                nums_sorted = sorted(
                    nums, key=lambda x: abs((x - expected) / (expected + 1e-9))
                )
                found = nums_sorted[0]
        if found is None:
            # fallback: not enough evidence
            items.append(
                {
                    "policy": "sum_check",
                    "dept": dept_str,
                    "status": "diff",
                    "expected": int(expected),
                    "found": 0,
                    "delta": int(expected),
                }
            )
            warn += 1
        else:
            delta = int(found) - int(expected)
            status = "ok" if (abs(delta) <= max(1, int(expected * tol))) else "diff"
            if status == "ok":
                ok += 1
            else:
                warn += 1
            items.append(
                {
                    "policy": "sum_check",
                    "dept": dept_str,
                    "status": status,
                    "expected": int(expected),
                    "found": int(found),
                    "delta": int(delta),
                    "evidence": evid,
                }
            )

    summary = {"ok": int(ok), "warn": int(warn), "fail": int(fail)}
    return {"validation_report": {"summary": summary, "items": items}}


# --- node_export_xlsx: 다운로드 파일명(meta) 반영 ---
def node_export_xlsx(
    cfg: Dict[str, Any], inputs: Dict[str, Any], ctx: Ctx
) -> Dict[str, Any]:
    table = _dig(inputs, cfg.get("table_in", "merge_xlsx.merged_table"))
    report = _dig(inputs, "validate_with_pdf.validation_report")
    # 기본 파일명(요구사항 반영)
    name = cfg.get(
        "filename",
        "2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx",
    )

    os.makedirs(ctx.art_dir, exist_ok=True)
    art_id = f"art-{ctx.run_id[:8]}"
    path = os.path.join(ctx.art_dir, f"{art_id}.xlsx")

    with pd.ExcelWriter(path) as w:
        (table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)).to_excel(
            w, index=False, sheet_name="merged"
        )
        if report:
            pd.DataFrame([report.get("summary", {})]).to_excel(
                w, index=False, sheet_name="summary"
            )
            pd.DataFrame(report.get("items", [])).to_excel(
                w, index=False, sheet_name="items"
            )

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


def _dig(obj: dict, dotted: str):
    """
    Resolve values from the flat outputs map.

    Priority:
      1) exact top-level key (incl. 'node.output')
      2) last-segment fallback (e.g., 'pdf_chunks')
      3) nested walking
    """
    # 1) exact top-level
    if dotted in obj:
        return obj[dotted]
    # 2) fallback to last segment
    if "." in dotted:
        last = dotted.split(".")[-1]
        if last in obj:
            return obj[last]
    # 3) nested walking
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def execute_stream(workflow: Dict[str, Any], ctx: Ctx):
    # generator of SSE-friendly events while executing nodes sequentially
    outputs: Dict[str, Any] = {}

    def ev(_type: str, node_id: str, message: str, detail: Dict[str, Any] = None):
        return {
            "type": _type,
            "nodeId": node_id,
            "message": message,
            "detail": detail or {},
            "ts": now_iso(),
        }

    yield ev(
        "PLAN",
        "plan",
        f"총 {len(workflow.get('nodes', []))}개 노드 실행 계획 수립",
        {"nodes": len(workflow.get("nodes", []))},
    )

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
