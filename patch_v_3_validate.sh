#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Patch v3: Fix validate_with_pdf numeric_only error and robust amount parsing
# - Cleans amount column (commas, () negatives, symbols) → float
# - Uses SeriesGroupBy.sum *without* numeric_only, after coercion
# - Case-insensitive dept matching; safer fallbacks

python - <<'PY'
import re
from pathlib import Path

p = Path('backend/engine.py')
s = p.read_text(encoding='utf-8')

new_func = r'''

def node_validate_with_pdf(cfg: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    # table_in: merge_xlsx.merged_table, vs_in (optional), tolerance
    table = _dig(inputs, cfg.get("table_in", "merge_xlsx.merged_table"))
    chunks = _dig(inputs, "parse_pdf.pdf_chunks") or []  # evidence source
    tol = float(cfg.get("tolerance", 0.005))

    import pandas as pd

    if isinstance(table, pd.DataFrame):
        df = table.copy()
    else:
        df = pd.DataFrame(table)

    if df.empty:
        return {
            "validation_report": {
                "summary": {"ok":0, "warn":0, "fail":1},
                "items": [ {"policy":"exists","dept":"*","status":"miss","evidence":[]} ]
            }
        }

    # normalize column names (string)
    df.columns = [str(c).strip() for c in df.columns]

    # auto-detect columns
    dept_col, amt_col = _auto_detect_columns(df)

    # --- Clean amount column into float ---
    import math

    def _clean_amount(x):
        if x is None:
            return None
        try:
            import pandas as pd
            if pd.isna(x):
                return None
        except Exception:
            pass
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x)
        s = s.strip()
        if not s:
            return None
        # remove currency/unit symbols, keep digits, sign, dot, parentheses
        # examples: "1,234", "(5,000)", "-120", "12,345.67원"
        neg = False
        if s.startswith('(') and s.endswith(')'):
            neg = True
            s = s[1:-1]
        s = s.replace(',', '')
        s = re.sub(r"[^0-9\.-]", "", s)
        if s in ("", "-", ".", "-."):
            return None
        try:
            v = float(s)
            if neg:
                v = -v
            return v
        except Exception:
            return None

    cleaned = df[amt_col].apply(_clean_amount)
    df['_amt_'] = pd.to_numeric(cleaned, errors='coerce')

    # group per dept; SeriesGroupBy.sum doesn't accept numeric_only, so we already coerced
    try:
        grouped = df.groupby(dept_col)['_amt_'].sum(min_count=1)
    except TypeError:
        # older pandas without min_count parameter
        grouped = df.groupby(dept_col)['_amt_'].sum()

    items = []
    ok = warn = fail = 0

    # index chunks by page and build lowercase text for matching
    by_page = {}
    for ch in chunks:
        pno = int(ch.get("page", 1))
        by_page.setdefault(pno, []).append(ch)

    def _norm(s):
        return str(s).lower()

    for dept, expected in grouped.items():
        if expected is None or (isinstance(expected, float) and math.isnan(expected)):
            expected = 0.0
        dept_str = str(dept)
        dept_norm = _norm(dept_str)

        # exists policy (case-insensitive)
        evid = []
        for ch in chunks:
            txt = _norm(ch.get("text", ""))
            if dept_norm and dept_norm in txt:
                evid.append({"page": int(ch.get("page",1)), "snippet": ch.get("text","")[:180]})
                break
        if evid:
            items.append({"policy":"exists", "dept": dept_str, "status":"ok", "evidence": evid})
            ok += 1
        else:
            items.append({"policy":"exists", "dept": dept_str, "status":"miss", "evidence": []})
            fail += 1

        # sum_check policy
        found = None
        if evid:
            p = evid[0]["page"]
            nums = []
            for c in by_page.get(p, []):
                nums.extend(_numbers_in_text(c.get("text", "")))
            if nums:
                nums.sort(key=lambda x: abs((x - expected) / (expected + 1e-9)))
                found = nums[0]
        # fallback: no evidence numbers on that page → no match
        if found is None:
            items.append({
                "policy":"sum_check", "dept": dept_str, "status":"diff",
                "expected": int(round(expected)), "found": 0,
                "delta": int(round(expected))
            })
            warn += 1
        else:
            delta = int(round(found)) - int(round(expected))
            status = "ok" if abs(delta) <= max(1, int(round(expected * tol))) else "diff"
            if status == "ok":
                ok += 1
            else:
                warn += 1
            items.append({
                "policy":"sum_check", "dept": dept_str, "status": status,
                "expected": int(round(expected)), "found": int(round(found)),
                "delta": int(delta), "evidence": evid
            })

    summary = {"ok": int(ok), "warn": int(warn), "fail": int(fail)}
    return {"validation_report": {"summary": summary, "items": items}}

'''

# Replace function body up to the next def node_export_xlsx
pattern = r"def\s+node_validate_with_pdf\([^\)]*\):[\s\S]*?def\s+node_export_xlsx\("
s = re.sub(pattern, new_func + "\n\ndef node_export_xlsx(", s)

p.write_text(s, encoding='utf-8')
print('[OK] Patched validate_with_pdf to robust numeric handling')
PY

echo "[DONE] Patch v3 applied. Restart server if not using --reload."
