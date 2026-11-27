"""AI gateway: one entry point for every AI call, with fallback and model-version tracking.

Primary provider first. On an outage, a schema failure, or a page the primary is unsure about,
the fallback is tried. If every provider fails, AdapterError is raised and the caller queues a
retry (fail closed, never a silent guess).
"""

import logging
from dataclasses import dataclass, field

from app.adapters.ai import AIProvider
from app.adapters.ai_schemas import AIResult, DocumentExtraction, LedgerExtraction, Transcript
from app.adapters.errors import AdapterError

log = logging.getLogger(__name__)

UNSURE_PAGE_CONFIDENCE = 0.6


@dataclass
class AIGateway:
    primary: AIProvider
    fallback: AIProvider | None = None
    calls: list[str] = field(default_factory=list)

    @property
    def sandbox(self) -> bool:
        return self.primary.sandbox

    def _providers(self) -> list[AIProvider]:
        return [p for p in (self.primary, self.fallback) if p is not None]

    def model_versions(self) -> dict[str, str]:
        out = {}
        for role, p in (("primary", self.primary), ("fallback", self.fallback)):
            if p is not None:
                out[role] = f"{p.name}:{p.model_for('vision')}"
        return out

    def extract_ledger(self, image: bytes, mime: str = "image/jpeg") -> AIResult[LedgerExtraction]:
        best: AIResult[LedgerExtraction] | None = None
        errors: list[str] = []
        for provider in self._providers():
            self.calls.append(f"{provider.name}.extract_ledger")
            try:
                value = provider.extract_ledger(image, mime)
            except AdapterError as exc:
                log.warning("extract_ledger failed on %s: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue
            result = AIResult[LedgerExtraction](
                value=value,
                provider=provider.name,
                model=provider.model_for("vision"),
                sandbox=provider.sandbox,
            )
            if best is None or value.page_confidence > best.value.page_confidence:
                best = result
            if value.page_confidence >= UNSURE_PAGE_CONFIDENCE:
                break
        if best is None:
            raise AdapterError("; ".join(errors) or "no AI provider")
        return best

    def extract_document(
        self, image: bytes, mime: str = "image/jpeg"
    ) -> AIResult[DocumentExtraction]:
        """Primary first; the fallback is asked when the primary fails or is unsure."""
        best: AIResult[DocumentExtraction] | None = None
        errors: list[str] = []
        for provider in self._providers():
            self.calls.append(f"{provider.name}.extract_document")
            try:
                value = provider.extract_document(image, mime)
            except AdapterError as exc:
                log.warning("extract_document failed on %s: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue
            result = AIResult[DocumentExtraction](
                value=value,
                provider=provider.name,
                model=provider.model_for("vision"),
                sandbox=provider.sandbox,
            )
            if best is None or value.confidence > best.value.confidence:
                best = result
            if value.confidence >= UNSURE_PAGE_CONFIDENCE:
                break
        if best is None:
            raise AdapterError("; ".join(errors) or "no AI provider")
        return best

    def transcribe(self, audio: bytes, language: str) -> AIResult[Transcript]:
        errors: list[str] = []
        for provider in self._providers():
            self.calls.append(f"{provider.name}.transcribe")
            try:
                value = provider.transcribe(audio, language)
            except AdapterError as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            return AIResult(
                value=value,
                provider=provider.name,
                model=provider.model_for("stt"),
                sandbox=provider.sandbox,
            )
        raise AdapterError("; ".join(errors))

    def synthesize(self, text: str, language: str) -> AIResult[bytes]:
        errors: list[str] = []
        for provider in self._providers():
            try:
                value = provider.synthesize(text, language)
            except AdapterError as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            return AIResult(
                value=value,
                provider=provider.name,
                model=provider.model_for("tts"),
                sandbox=provider.sandbox,
            )
        raise AdapterError("; ".join(errors))

    def generate(self, system: str, prompt: str, language: str) -> AIResult[str]:
        errors: list[str] = []
        for provider in self._providers():
            self.calls.append(f"{provider.name}.generate")
            try:
                value = provider.generate(system, prompt, language)
            except AdapterError as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            return AIResult(
                value=value,
                provider=provider.name,
                model=provider.model_for("llm"),
                sandbox=provider.sandbox,
            )
        raise AdapterError("; ".join(errors))
