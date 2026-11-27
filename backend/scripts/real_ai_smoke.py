"""Real AI smoke test: calls the real Sarvam and fallback adapters (never in the test suite).

Keys may be placeholders such as SARVAM_API_KEY=proxy when the session's network proxy injects
the real key. Every call is recorded with its exact error; nothing here changes the mocks.

Usage: SARVAM_API_KEY=proxy GEMINI_API_KEY=proxy uv run python -m scripts.real_ai_smoke
Writes eval/real_ai_smoke.md.
"""

import json
import os
import socket
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.adapters.ai import AnthropicAI, GeminiAI, SarvamAI
from app.adapters.ai_schemas import LedgerExtraction
from app.adapters.errors import AdapterError, NotConfiguredError, is_placeholder
from app.core.config import Settings
from app.evaluation.extraction_eval import GOLDEN_DIR, load_golden, sandbox_golden

OUT = Path(__file__).resolve().parents[1] / "eval" / "real_ai_smoke.md"
HOSTS = ["api.sarvam.ai", "generativelanguage.googleapis.com", "api.anthropic.com"]


def reach(host: str) -> str:
    """Can this session open HTTPS to the host through the proxy? Reports the exact outcome."""
    try:
        r = httpx.get(f"https://{host}/", timeout=15)
        return f"reachable (HTTP {r.status_code} on /)"
    except httpx.HTTPError as exc:
        return f"not reachable: {type(exc).__name__}: {exc}"


def key_state(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        return "not set"
    return "placeholder (proxy injects)" if is_placeholder(v) else "set (real value in env)"


def run(label: str, fn: Callable[[], Any]) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        out = fn()
        return {
            "call": label,
            "ok": True,
            "ms": round((time.monotonic() - t0) * 1000),
            "result": out,
        }
    except (AdapterError, NotConfiguredError, httpx.HTTPError, ValueError, OSError) as exc:
        cause = exc.__cause__
        return {
            "call": label,
            "ok": False,
            "ms": round((time.monotonic() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}"
            + (f" | cause: {type(cause).__name__}: {cause}" if cause else ""),
        }
    except Exception as exc:
        return {
            "call": label,
            "ok": False,
            "ms": round((time.monotonic() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-600:],
        }


def score(got: LedgerExtraction, want: LedgerExtraction) -> str:
    n = len(want.entries)
    amounts = sum(
        1
        for i, w in enumerate(want.entries)
        if i < len(got.entries) and got.entries[i].amount_paise == w.amount_paise
    )
    return (
        f"{len(got.entries)} entries read, exact amounts {amounts}/{n}, page confidence "
        f"{got.page_confidence}"
    )


def sample_clip() -> tuple[bytes | None, str]:
    for p in sorted(GOLDEN_DIR.glob("*.wav")):
        return p.read_bytes(), p.name
    return None, "no sample clip in eval/golden (*.wav); STT is tried on a TTS clip if TTS works"


def main() -> None:
    s = Settings()
    results: list[dict[str, Any]] = []
    pages = load_golden()[:3] or sandbox_golden(2)
    real_pages = bool(load_golden())
    sarvam: SarvamAI | None = None
    try:
        sarvam = SarvamAI(s)
    except NotConfiguredError as exc:
        results.append({"call": "Sarvam adapter", "ok": False, "error": str(exc)})
    if sarvam is not None:
        for p in pages:
            results.append(
                run(
                    f"Sarvam Vision ({s.sarvam_vision_model}) on {p.name}",
                    lambda p=p: score(sarvam.extract_ledger(p.image, p.mime), p.label),
                )
            )
        tts = run(
            f"Sarvam TTS ({s.sarvam_tts_model}) hi",
            lambda: len(sarvam.synthesize("शर्मा जी से चार हज़ार रुपये मिले", "hi")),
        )
        results.append(tts)
        clip, clip_note = sample_clip()
        if clip is None and tts["ok"]:
            clip, clip_note = (
                sarvam.synthesize("शर्मा जी से चार हज़ार रुपये मिले", "hi"),
                "clip made by Sarvam TTS",
            )
        if clip is not None:
            results.append(
                run(
                    f"Sarvam STT ({s.sarvam_stt_model}) on {clip_note}",
                    lambda: sarvam.transcribe(clip, "hi").text,
                )
            )
        else:
            results.append(
                {
                    "call": f"Sarvam STT ({s.sarvam_stt_model})",
                    "ok": False,
                    "error": f"not run: {clip_note}, and TTS failed",
                }
            )
        results.append(
            run(
                f"Sarvam LLM ({s.sarvam_llm_model})",
                lambda: sarvam.generate("Reply with one word.", "Say OK", "en")[:80],
            )
        )
    vendor = s.fallback_ai_vendor
    fallback: GeminiAI | AnthropicAI | None = None
    try:
        fallback = AnthropicAI(s) if vendor == "anthropic" else GeminiAI(s)
    except NotConfiguredError as exc:
        results.append({"call": f"Fallback adapter ({vendor})", "ok": False, "error": str(exc)})
    if fallback is not None:
        for p in pages[:2]:
            results.append(
                run(
                    f"Fallback vision ({fallback.name}:{fallback.model_for('vision')}) on {p.name}",
                    lambda p=p: score(fallback.extract_ledger(p.image, p.mime), p.label),
                )
            )
        results.append(
            run(
                f"Fallback LLM ({fallback.name})",
                lambda: fallback.generate("Reply with one word.", "Say OK", "en")[:80],
            )
        )
    write(s, results, real_pages, [(h, reach(h)) for h in HOSTS])


def diagnose(results: list[dict[str, Any]], hosts: list[tuple[str, str]]) -> list[str]:
    errors = " ".join(str(r.get("error", "")) for r in results)
    out = []
    if "agent proxy: no rule" in errors and "sarvam" in errors:
        out.append(
            "- **Sarvam is blocked by this environment's network policy** (the proxy refuses "
            "`api.sarvam.ai`). Allow the host and save the key as a network secret with "
            "header `api-subscription-key`, or run this script where Sarvam is reachable "
            "with a real `SARVAM_API_KEY`."
        )
    if "API_KEY_INVALID" in errors or "API key not valid" in errors:
        out.append(
            "- **Gemini is reachable but no key reached it**: the placeholder was sent as "
            "is, so no network secret is configured for `generativelanguage.googleapis.com`"
            " (header `x-goog-api-key`). Add one, or set a real `GEMINI_API_KEY`."
        )
    if not out and not any(r.get("ok") for r in results):
        out.append("- Every call failed; see the exact errors above.")
    if any(r.get("ok") for r in results):
        out.append(
            "- Successful calls show the real adapters, schemas and parsing work end to end."
        )
    out.append(
        "- The app keeps using the mocks (labelled Sandbox) until a real call succeeds and "
        "the keys are configured; nothing in the test suite depends on these calls."
    )
    return out


def write(
    s: Settings, results: list[dict[str, Any]], real_pages: bool, hosts: list[tuple[str, str]]
) -> None:
    ok = sum(1 for r in results if r.get("ok"))
    lines = [
        "# Real AI smoke test",
        "",
        f"Run {datetime.now(UTC).isoformat(timespec='seconds')} on {socket.gethostname()}.",
        f"**{ok}/{len(results)} calls succeeded.** Mocks are unchanged; the test suite never "
        "calls real APIs.",
        "",
        "## Setup",
        "",
        f"- Images: {'real golden pages' if real_pages else 'synthetic sandbox ledger pages'}",
        f"- `SARVAM_API_KEY`: {key_state('SARVAM_API_KEY')}; base URL {s.sarvam_base_url}",
        f"- `GEMINI_API_KEY`: {key_state('GEMINI_API_KEY')}; "
        f"`ANTHROPIC_API_KEY`: {key_state('ANTHROPIC_API_KEY')}; fallback vendor "
        f"{s.fallback_ai_vendor}",
        "",
        "## Network",
        "",
    ]
    lines += [f"- `{h}`: {state}" for h, state in hosts]
    lines += ["", "## Calls", "", "| Call | Result | ms |", "| --- | --- | --- |"]
    for r in results:
        err = " ".join(str(r.get("error", "")).split()).replace("|", "/")
        res = (
            f"ok: {json.dumps(r['result'], ensure_ascii=False)[:160]}"
            if r.get("ok")
            else f"**failed**: `{err[:420]}`"
        )
        lines.append(f"| {r['call']} | {res} | {r.get('ms', '')} |")
    lines += ["", "## What this means", "", *diagnose(results, hosts)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(OUT.read_text())


if __name__ == "__main__":
    main()
