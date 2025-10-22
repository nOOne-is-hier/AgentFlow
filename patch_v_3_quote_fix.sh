#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Fix SyntaxError in backend/engine.py caused by r'-\1' line break -> use \g<1>

python - <<'PY'
import re
from pathlib import Path
p = Path('backend/engine.py')
s = p.read_text(encoding='utf-8')

# 1) Exact simple replacement first
simple_old = "s = s.str.replace(r'^\\((.*)\\)$', r'-\\1', regex=True)"
s = s.replace(simple_old, "s = s.str.replace(r'^\\((.*)\\)$', r'-\\g<1>', regex=True)")

# 2) Generic safety: any str.replace(... r'-\1', regex=True) on the ( ... ) pattern
s = re.sub(
    r"str\.replace\(\s*r'\^\\\((\.\*?)\\\)\$'\s*,\s*r'-\\1'\s*,\s*regex=True\s*\)",
    r"str.replace(r'^\\((\\1))$', r'-\\g<1>', regex=True)",
    s
)

p.write_text(s, encoding='utf-8')
print('[OK] Converted backreference r"-\\1" to r"-\\g<1>" to avoid raw-string + backslash EOL issues')
PY

echo "[DONE] Quote/backreference fix applied. If the server crashed, re-run ./run_backend.sh"