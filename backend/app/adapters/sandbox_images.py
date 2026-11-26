"""Sandbox ledger images: a drawn page that also carries its ground truth in a PNG text chunk,
so the mock vision adapter can 'read' it. Used by seed data, tests and the demo."""

import io
import json
from typing import Any

from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo


def ledger_png(extraction: dict[str, Any], title: str = "Bahi Khata", noise: str = "") -> bytes:
    img = Image.new("RGB", (800, 1000), (250, 245, 225))
    draw = ImageDraw.Draw(img)
    draw.text((40, 30), title, fill=(120, 20, 20))
    y = 90
    for e in extraction.get("entries", []):
        line = (
            f"{e.get('entry_date') or '--'}   {e.get('party_text') or ''}   "
            f"{e['amount_paise'] / 100:.0f}   {'jama' if e['direction'] == 'in' else 'naam'}"
        )
        draw.text((40, y), line, fill=(20, 20, 80))
        draw.line((30, y + 30, 770, y + 30), fill=(200, 160, 160))
        y += 40
    if extraction.get("page_total_paise") is not None:
        draw.text((40, y + 20), f"Total {extraction['page_total_paise'] / 100:.0f}", fill=(0, 0, 0))
    if noise:
        draw.text((40, 950), noise, fill=(0, 0, 0))
    info = PngInfo()
    info.add_itxt("ktp-ledger", json.dumps(extraction), zip=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()
