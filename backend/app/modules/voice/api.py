"""Voice playback for every screen (Bulbul v3 through the AI gateway)."""

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.errors import DomainError

router = APIRouter(prefix="/voice", tags=["voice"])

LANGS = {"hi", "en", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "od"}


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    language: str = "hi"


@router.post("/tts")
def tts(body: TTSIn) -> Response:
    if body.language not in LANGS:
        raise DomainError("Language not supported", "bad_language")
    try:
        audio = get_adapters().ai.synthesize(body.text, body.language)
    except AdapterError as exc:
        raise DomainError("Voice is not available right now", "tts_down", 503) from exc
    return Response(
        content=audio.value,
        media_type="audio/wav",
        headers={
            "X-Sandbox": "1" if audio.sandbox else "0",
            "Cache-Control": "private, max-age=86400",
        },
    )
