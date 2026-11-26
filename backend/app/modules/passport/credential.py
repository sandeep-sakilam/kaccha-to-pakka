"""The Business Trust Passport as a W3C Verifiable Credential, signed with our Ed25519 key.

Two signed forms: the full VC (JSON, for API and PDF) and a compact payload carried inside the
QR code, so a lender can verify the signature offline. Live status (valid, revoked, expired,
on hold) always comes from the status endpoint.
"""

import base64
import json
import zlib
from datetime import datetime
from typing import Any

from app.core import signing
from app.core.config import get_settings

VC_CONTEXT = ["https://www.w3.org/ns/credentials/v2"]
ISSUER_NAME = "Kaccha to Pakka"


def issuer_did() -> str:
    host = get_settings().public_base_url.split("://", 1)[-1].split("/")[0].replace(":", "%3A")
    return f"did:web:{host}"


def build_vc(
    passport_id: str,
    business: dict[str, Any],
    assessment: dict[str, Any],
    valid_from: datetime,
    valid_until: datetime,
    sandbox: bool,
) -> dict[str, Any]:
    base = get_settings().public_base_url.rstrip("/")
    return {
        "@context": VC_CONTEXT,
        "type": ["VerifiableCredential", "BusinessTrustPassport"],
        "id": f"urn:uuid:{passport_id}",
        "issuer": {"id": issuer_did(), "name": ISSUER_NAME},
        "validFrom": valid_from.isoformat(),
        "validUntil": valid_until.isoformat(),
        "credentialSubject": {
            "id": f"urn:ktp:business:{business['id']}",
            "name": business["name"],
            "category": business["category"],
            "city": business.get("city"),
            "band": assessment["band"],
            "confidence": assessment["confidence"],
            "assessmentStatus": assessment["status"],
            "pillars": assessment["pillars"],
            "reasons": {
                k: [r["code"] for r in v]
                for k, v in assessment["reasons"].items()
                if k in {"positives", "gaps", "improve"}
            },
            "rulesVersion": assessment["rules_version"],
            "assessmentId": assessment["id"],
            "sandbox": sandbox,
            "disclaimer": "Evidence and verification only. Not a credit score; the lender decides.",
        },
        "credentialStatus": {
            "id": f"{base}/api/passports/{passport_id}/status",
            "type": "KtpLiveStatus",
        },
    }


def sign_vc(vc: dict[str, Any]) -> dict[str, Any]:
    proof_value = signing.sign(vc)
    return {
        **vc,
        "proof": {
            "type": "DataIntegrityProof",
            "cryptosuite": "eddsa-jcs-2022",
            "verificationMethod": f"{issuer_did()}#{signing.key_id()}",
            "proofPurpose": "assertionMethod",
            "proofValue": proof_value,
        },
    }


def verify_vc(signed: dict[str, Any], public_key: str | None = None) -> bool:
    proof = signed.get("proof") or {}
    body = {k: v for k, v in signed.items() if k != "proof"}
    return bool(proof.get("proofValue")) and signing.verify(body, proof["proofValue"], public_key)


def compact(signed_vc: dict[str, Any]) -> dict[str, Any]:
    s = signed_vc["credentialSubject"]
    return {
        "v": 1,
        "id": signed_vc["id"].removeprefix("urn:uuid:"),
        "n": s["name"],
        "c": s["category"],
        "b": s["band"],
        "cf": s["confidence"],
        "st": s["assessmentStatus"],
        "vu": signed_vc["validUntil"][:10],
        "r": s["rulesVersion"],
        "sb": s["sandbox"],
        "kid": signing.key_id(),
    }


def qr_token(signed_vc: dict[str, Any]) -> str:
    payload = compact(signed_vc)
    sig = signing.sign(payload)
    raw = zlib.compress(
        json.dumps({"p": payload, "s": sig}, separators=(",", ":"), ensure_ascii=False).encode(), 9
    )
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def read_qr_token(token: str, public_key: str | None = None) -> tuple[bool, dict[str, Any]]:
    """Offline check of a QR token: returns (signature_ok, payload)."""
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        data = json.loads(raw)
        payload, sig = data["p"], data["s"]
    except (ValueError, KeyError, zlib.error, json.JSONDecodeError):
        return False, {}
    return signing.verify(payload, sig, public_key), payload


def verify_url(passport_id: str, token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/v/{passport_id}#{token}"
