#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

ENGINE_FILE="backend/engine.py"

# Hotfix: robust _dig() + safe embed_pdf chunk fallback
# - Fixes NoneType errors when resolving namespaced keys like "parse_pdf.pdf_chunks"
# - Makes embed step resilient if chunks are missing

python - <<'PY'
import re
from pathlib import Path

p = Path('backend/engine.py')
s = p.read_text(encoding='utf-8')

# --- Replace _dig() until the start of execute_stream() ---
new_dig = '''
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
    if '.' in dotted:
        last = dotted.split('.')[-1]
        if last in obj:
            return obj[last]
    # 3) nested walking
    cur = obj
    for part in dotted.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur

'''

s = re.sub(r"def\s+_dig\(.*?\):[\s\S]*?(?=def\s+execute_stream\()", new_dig, s)

# --- Make embed_pdf resilient ---
# Replace the assignment to 'chunks =' inside node_embed_pdf with a safe fallback chain
s = re.sub(
    r"(def\s+node_embed_pdf\([^\)]*\):\s*\n\s*#.*?\n\s*key\s*=.*?\n\s*)chunks\s*=.*?\n",
    r"\1chunks = _dig(inputs, key) or _dig(inputs, 'pdf_chunks') or []\n",
    s,
    flags=re.S,
)

p.write_text(s, encoding='utf-8')
print('[OK] Patched engine._dig and embed_pdf fallback')
PY

echo "[DONE] Hotfix applied. Re-run the backend if needed."
