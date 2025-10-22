from __future__ import annotations
import os, re, json, io
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .settings import TMP_DIR, ART_DIR
from .vectorstore import ChromaVS, VSDoc, new_id

KST = timezone.utc  # 간소화: 표시는 클라이언트에서


def now_iso():
    return datetime.now(KST).isoformat()


@dataclass
class Ctx:
    run_id: str
    storage: str
    art_dir: str


# ---------- Helpers ----------
def _ensure_df(obj) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, str) and os.path.exists(obj):
        low = obj.lower()
        if low.endswith(".parquet"):
            return pd.read_parquet(obj)
        if low.endswith(".xlsx"):
            return pd.read_excel(obj, engine="openpyxl")
        if low.endswith(".csv"):
            return pd.read_csv(obj)
    if isinstance(obj, (dict, list)):
        return pd.DataFrame(obj)
    return pd.DataFrame()


def _dig(obj: dict, dotted: str):
    if dotted in obj:
        return obj[dotted]
    if "." in dotted:
        last = dotted.split(".")[-1]
        if last in obj:
            return obj[last]
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _numbers_in_text(s: str) -> List[int]:
    ns = re.findall(r"\d{1,3}(?:,\d{3})*|\d+", s)
    out = []
    for n in ns:
        try:
            out.append(int(n.replace(",", "")))
        except Exception:
            pass
    return out


# ---------- PDF ----------
try:
    import fitz  # PyMuPDF

    USE_FITZ = True
except Exception:
    USE_FITZ = False
    from pypdf import PdfReader  # lazy fallback


def node_parse_pdf(cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = cfg["pdf_path"]
    chunk_size = int(cfg.get("chunk_size", 1200))
    overlap = int(cfg.get("overlap", 200))
    chunks: List[Dict[str, Any]] = []

    if USE_FITZ:
        doc = fitz.open(path)
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            text = re.sub(r"\s+", " ", text)
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                snippet = text[start:end]
                chunks.append({"page": i, "text": snippet})
                if end == len(text):
                    break
                start = max(0, end - overlap)
    else:
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            text = re.sub(r"\s+", " ", text)
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

    return {"pdf_chunks": chunks, "pdf_pages": int(chunks[-1]["page"]) if chunks else 0}


# ---------- VectorStore(Chroma) ----------
def node_embed_pdf_to_chroma(
    cfg: Dict[str, Any], inputs: Dict[str, Any]
) -> Dict[str, Any]:
    key = cfg.get("chunks_in", "parse_pdf.pdf_chunks")
    chunks: List[Dict[str, Any]] = _dig(inputs, key) or []
    if not chunks:
        return {"vs_ref": None, "vs_count": 0}

    vs = ChromaVS()
    # 리셋 여부 옵션(기본: 덮어쓰기 방지 위해 새 id 부여)
    reset = bool(cfg.get("reset", True))
    if reset:
        vs.reset()

    docs: List[VSDoc] = []
    for idx, ch in enumerate(chunks, start=1):
        docs.append(
            VSDoc(
                id=new_id("pdf"),
                text=ch.get("text", "")[:4000],
                metadata={"page": int(ch.get("page", 1)), "chunk_index": idx},
            )
        )
    vs.upsert(docs)
    return {"vs_ref": "chroma://", "vs_count": len(docs)}


# ---------- XLSX 병합 ----------
def node_merge_xlsx(
    cfg: Dict[str, Any], inputs: Dict[str, Any], ctx: Ctx
) -> Dict[str, Any]:
    import pandas as pd

    def read_one(xp: str) -> List[pd.DataFrame]:
        if not xp or not os.path.exists(xp):
            raise FileNotFoundError(xp)
        sheets = pd.read_excel(xp, sheet_name=None, engine="openpyxl")
        out = []
        for name, df in sheets.items():
            d = df.copy()
            d["__sheet__"] = name
            d["__file__"] = os.path.basename(xp)
            out.append(d)
        return out

    paths = cfg.get("xlsx_paths") or []
    frames: List[pd.DataFrame] = []
    for xp in paths:
        frames.extend(read_one(xp))

    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    merged.columns = [str(c).strip() for c in merged.columns]

    # 저장(Parquet->CSV 폴백)
    from .settings import TMP_DIR

    parquet_path = os.path.join(TMP_DIR, f"{ctx.run_id[:8]}_merged.parquet")
    csv_path = os.path.join(TMP_DIR, f"{ctx.run_id[:8]}_merged.csv")
    out_path = None
    try:
        merged.to_parquet(parquet_path, index=False)
        out_path = parquet_path
    except Exception:
        merged.to_csv(csv_path, index=False)
        out_path = csv_path

    return {
        "merged_table": merged,
        "merged_path": out_path,
        "merged_rows": int(len(merged)),
    }


# ---------- 검증 (exists/sum_check) ----------
def _auto_detect_columns(df: pd.DataFrame) -> Tuple[str, str]:
    cand_dept = [
        c
        for c in df.columns
        if any(k in str(c) for k in ["부서", "부문", "팀", "과", "기관", "부서명"])
    ]
    dept_col = cand_dept[0] if cand_dept else str(df.columns[0])
    num_cols = [
        c
        for c in df.columns
        if (df[c].dtype.kind in "fi")
        or re.search(r"(금액|합계|총액|세출|지출|예산액|기정액|비교증감)", str(c))
    ]
    amt_col = num_cols[0] if num_cols else str(df.columns[-1])
    return dept_col, amt_col


def node_validate_with_pdf(
    cfg: Dict[str, Any], inputs: Dict[str, Any]
) -> Dict[str, Any]:
    import pandas as pd
    from .vectorstore import ChromaVS

    table_ref = _dig(inputs, cfg.get("table_in", "merge_xlsx.merged_table"))
    df = _ensure_df(table_ref)
    tol = float(cfg.get("tolerance", 0.005))

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

    # 금액 전처리
    s = df[amt_col].astype(str).str.strip()
    s = (
        s.str.replace(r"\(([^)]+)\)", r"-\1", regex=True)
        .str.replace(",", "", regex=False)
        .str.replace(r"[^0-9\.\-]", "", regex=True)
    )
    df["_amt_"] = pd.to_numeric(s, errors="coerce")

    grouped = df.groupby(dept_col)["_amt_"].sum(numeric_only=True).fillna(0)

    vs = ChromaVS()
    items = []
    ok = warn = fail = 0

    for dept, expected in grouped.items():
        dept_str = str(dept).strip()
        # exists: 벡터 질의
        q = f"{dept_str} 부서 예산 총괄 표 또는 조직 표기"
        hits = vs.query(q, k=3)
        evid = []
        for h in hits:
            page = int(h["metadata"].get("page", 1))
            text = h["text"][:180]
            evid.append({"page": page, "snippet": text})
        if evid:
            items.append(
                {
                    "policy": "exists",
                    "dept": dept_str,
                    "status": "ok",
                    "evidence": evid[:1],
                }
            )
            ok += 1
        else:
            items.append(
                {"policy": "exists", "dept": dept_str, "status": "miss", "evidence": []}
            )
            fail += 1

        # sum_check: 해당 증거 페이지의 숫자 중 기대값과 가까운 수치 선택
        found = None
        if evid:
            nums = _numbers_in_text(" ".join([e["snippet"] for e in evid]))
            if nums:
                nums_sorted = sorted(
                    nums, key=lambda x: abs((x - expected) / (abs(expected) + 1e-9))
                )
                found = nums_sorted[0]

        if found is None:
            items.append(
                {
                    "policy": "sum_check",
                    "dept": dept_str,
                    "status": "diff",
                    "expected": int(expected),
                    "found": 0,
                    "delta": int(expected),
                    "evidence": evid[:1],
                }
            )
            warn += 1
        else:
            delta = int(found) - int(expected)
            status = "ok" if abs(delta) <= max(1, int(abs(expected) * tol)) else "diff"
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
                    "evidence": evid[:1],
                }
            )

    return {
        "validation_report": {
            "summary": {"ok": int(ok), "warn": int(warn), "fail": int(fail)},
            "items": items,
        }
    }


# ---------- Export (검증결과는 포함하지 않음) ----------
def node_export_xlsx(
    cfg: Dict[str, Any], inputs: Dict[str, Any], ctx: Ctx
) -> Dict[str, Any]:
    df = _ensure_df(_dig(inputs, cfg.get("table_in", "merge_xlsx.merged_table")))
    name = cfg.get(
        "filename",
        "2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx",
    )

    art_id = f"art-{ctx.run_id[:8]}"
    path = os.path.join(ctx.art_dir, f"{art_id}.xlsx")
    with pd.ExcelWriter(path) as w:
        df.to_excel(w, index=False, sheet_name="merged")

    meta_path = os.path.join(ctx.art_dir, f"{art_id}.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"display_name": name}, f, ensure_ascii=False, indent=2)

    return {"artifact_path": path, "artifact_id": art_id}


# ---------- 순차 실행기 (OBS 세분화) ----------
NODE_IMPLS = {
    "parse_pdf": node_parse_pdf,
    "embed_pdf": node_embed_pdf_to_chroma,
    "build_vectorstore": lambda cfg, inputs, ctx: {
        "vs_ref": "chroma://"
    },  # 호환용 더미
    "merge_xlsx": node_merge_xlsx,
    "validate_with_pdf": node_validate_with_pdf,
    "export_xlsx": node_export_xlsx,
}


def execute_stream(workflow: Dict[str, Any], ctx: Ctx):
    outputs: Dict[str, Any] = {}

    def ev(
        _type: str, node_id: str, message: str, detail: Dict[str, Any] | None = None
    ):
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
        nid, ntype = node["id"], node["type"]
        cfg = node.get("config", {}) or {}
        yield ev("ACTION", nid, f"{nid}({ntype}) 시작")

        impl = NODE_IMPLS.get(ntype)
        if not impl:
            yield ev("SUMMARY", nid, f"{nid} 실패: no impl for {ntype}")
            raise RuntimeError(f"no impl for {ntype}")

        try:
            if ntype in ("validate_with_pdf",):
                out = impl(cfg, {**outputs})
            elif ntype in ("merge_xlsx", "export_xlsx"):
                out = impl(cfg, {**outputs}, ctx)
            elif ntype in ("embed_pdf", "build_vectorstore"):
                out = (
                    impl(cfg, {**outputs}, ctx)
                    if impl.__code__.co_argcount >= 3
                    else impl(cfg, {**outputs})
                )
            else:
                out = impl(cfg)

            # OBS 세분화
            if ntype == "parse_pdf":
                yield ev(
                    "OBS",
                    nid,
                    "PDF 청킹 완료",
                    {
                        "chunks": len(out.get("pdf_chunks", [])),
                        "pages": out.get("pdf_pages", 0),
                    },
                )
            if ntype == "embed_pdf":
                yield ev(
                    "OBS", nid, "임베딩/색인 완료", {"count": out.get("vs_count", 0)}
                )
            if ntype == "merge_xlsx":
                yield ev(
                    "OBS", nid, "XLSX 병합 완료", {"rows": out.get("merged_rows", 0)}
                )
            if ntype == "validate_with_pdf":
                s = out.get("validation_report", {}).get("summary", {})
                yield ev(
                    "OBS",
                    nid,
                    "검증 요약",
                    {
                        "ok": s.get("ok", 0),
                        "warn": s.get("warn", 0),
                        "fail": s.get("fail", 0),
                    },
                )
            if ntype == "export_xlsx":
                yield ev(
                    "OBS", nid, "산출물 경로", {"artifact_id": out.get("artifact_id")}
                )

            for k, v in out.items():
                outputs[k] = v
                outputs[f"{nid}.{k}"] = v

            yield ev("SUMMARY", nid, f"{nid} 완료", {"keys": list(out.keys())})
        except Exception as e:
            yield ev("SUMMARY", nid, f"{nid} 실패: {e.__class__.__name__}: {e}")
            raise

    art = outputs.get("artifact_id") or outputs.get("export.artifact_id")
    yield ev("SUMMARY", "export", "산출물 생성", {"artifactId": art})
