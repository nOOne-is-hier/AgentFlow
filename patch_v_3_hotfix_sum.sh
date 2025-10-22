#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Quick hotfix for: TypeError: Cannot use numeric_only=True with SeriesGroupBy.sum and non-numeric dtypes.
# It rewrites the offending line in backend/engine.py and coerces the amount column to numeric safely.

python - <<'PY'
import re
from pathlib import Path
p = Path('backend/engine.py')
src = p.read_text(encoding='utf-8')

# Regex to find the grouped sum with numeric_only=True
pat = re.compile(r"(?P<indent>\s*)grouped\s*=\s*df\.groupby\(\s*dept_col\s*\)\s*\[\s*amt_col\s*\]\s*\.sum\(\s*numeric_only\s*=\s*True\s*\)")

if not pat.search(src):
    print('[INFO] No numeric_only=True pattern found; nothing to patch.')
else:
    repl = ("\g<indent>s = df[amt_col].astype(str).str.strip()\n"
            "\g<indent>s = s.str.replace(r'^\\((.*)\\)$', r'-\\1', regex=True)  # (1,234) -> -1,234\n"
            "\g<indent>s = s.str.replace(',', '', regex=False)\n"
            "\g<indent>s = s.str.replace(r'[^0-9\\.\\-]', '', regex=True)\n"
            "\g<indent>df['_amt_'] = pd.to_numeric(s, errors='coerce')\n"
            "\g<indent>grouped = df.groupby(dept_col)['_amt_'].sum()")
    src = pat.sub(repl, src)
    p.write_text(src, encoding='utf-8')
    print('[OK] Replaced numeric_only=True usage with safe coercion + sum().')
PY

echo "[DONE] Hotfix applied. Restart backend if not using --reload."
