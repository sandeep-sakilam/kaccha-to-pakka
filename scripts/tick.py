"""Tick a backlog item in PROGRESS.md and set the Current line.

python3 scripts/tick.py F07                       tick F07; Current = next unchecked item
python3 scripts/tick.py F38 feat/f39-explanation   Current = the given next branch
"""

import re
import sys
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "PROGRESS.md"
text = path.read_text()
fid = sys.argv[1]
text = re.sub(rf"^- \[ \] {fid} ", f"- [x] {fid} ", text, flags=re.M)
if len(sys.argv) > 2:
    current = f"Current: none; next is `{sys.argv[2]}`"
else:
    nxt = re.search(r"^- \[ \] (F\d\d) .*\(`(.+?)`\)$", text, flags=re.M)
    current = f"Current: none; next is `{nxt.group(2)}`" if nxt else "Current: none; backlog complete"
text = re.sub(r"^Current:.*$", current, text, flags=re.M)
path.write_text(text)
