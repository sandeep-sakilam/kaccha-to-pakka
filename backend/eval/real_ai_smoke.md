# Real AI smoke test

Run 2026-11-27T15:33:58+00:00 on vm.
**0/8 calls succeeded.** Mocks are unchanged; the test suite never calls real APIs.

## Setup

- Images: synthetic sandbox ledger pages
- `SARVAM_API_KEY`: placeholder (proxy injects); base URL https://api.sarvam.ai
- `GEMINI_API_KEY`: placeholder (proxy injects); `ANTHROPIC_API_KEY`: not set; fallback vendor gemini

## Network

- `api.sarvam.ai`: not reachable: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host)
- `generativelanguage.googleapis.com`: reachable (HTTP 404 on /)
- `api.anthropic.com`: reachable (HTTP 404 on /)

## Calls

| Call | Result | ms |
| --- | --- | --- |
| Sarvam Vision (sarvam-vision) on sandbox-00 | **failed**: `AdapterError: sarvam /v1/chat/completions: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host) / cause: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host)` | 272 |
| Sarvam Vision (sarvam-vision) on sandbox-01 | **failed**: `AdapterError: sarvam /v1/chat/completions: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host) / cause: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host)` | 7 |
| Sarvam TTS (bulbul:v3) hi | **failed**: `AdapterError: sarvam /text-to-speech: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host) / cause: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host)` | 5 |
| Sarvam STT (saaras:v3) | **failed**: `not run: no sample clip in eval/golden (*.wav); STT is tried on a TTS clip if TTS works, and TTS failed` |  |
| Sarvam LLM (sarvam-105b) | **failed**: `AdapterError: sarvam /v1/chat/completions: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host) / cause: ProxyError: 403 Forbidden (agent proxy: no rule or network setting allows this host)` | 256 |
| Fallback vision (gemini:gemini-2.5-flash) on sandbox-00 | **failed**: `AdapterError: gemini: HTTP 400 from generativelanguage.googleapis.com: { "error": { "code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "details": [ { "@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID", "domain": "googleapis.com / cause: HTTPStatusError: Client error '400 Bad Request' for url 'https://generativelanguage.googleapis.com/` | 36 |
| Fallback vision (gemini:gemini-2.5-flash) on sandbox-01 | **failed**: `AdapterError: gemini: HTTP 400 from generativelanguage.googleapis.com: { "error": { "code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "details": [ { "@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID", "domain": "googleapis.com / cause: HTTPStatusError: Client error '400 Bad Request' for url 'https://generativelanguage.googleapis.com/` | 16 |
| Fallback LLM (gemini) | **failed**: `AdapterError: gemini: HTTP 400 from generativelanguage.googleapis.com: { "error": { "code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "details": [ { "@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID", "domain": "googleapis.com / cause: HTTPStatusError: Client error '400 Bad Request' for url 'https://generativelanguage.googleapis.com/` | 20 |

## What this means

- **Sarvam is blocked by this environment's network policy** (the proxy refuses `api.sarvam.ai`). Allow the host and save the key as a network secret with header `api-subscription-key`, or run this script where Sarvam is reachable with a real `SARVAM_API_KEY`.
- **Gemini is reachable but no key reached it**: the placeholder was sent as is, so no network secret is configured for `generativelanguage.googleapis.com` (header `x-goog-api-key`). Add one, or set a real `GEMINI_API_KEY`.
- The app keeps using the mocks (labelled Sandbox) until a real call succeeds and the keys are configured; nothing in the test suite depends on these calls.
