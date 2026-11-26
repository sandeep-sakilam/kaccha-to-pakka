import copy
import io

import pdfplumber
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.passport import credential
from app.modules.passport.pdf import render_html
from app.modules.passport.service import issue
from tests.conftest import setup_business
from tests.test_trust_engine import strong_business


def test_issue_signed_vc_and_qr(db: Session) -> None:
    biz = strong_business(db)
    p = issue(db, biz, "test")
    vc = p.vc_json
    assert vc["type"] == ["VerifiableCredential", "BusinessTrustPassport"]
    assert vc["credentialSubject"]["band"] in {"A", "B"} and p.status == "valid"
    assert credential.verify_vc(vc)
    forged = copy.deepcopy(vc)
    forged["credentialSubject"]["band"] = "A" if vc["credentialSubject"]["band"] != "A" else "B"
    assert not credential.verify_vc(forged)
    token = credential.qr_token(vc)
    ok, payload = credential.read_qr_token(token)
    assert ok and payload["b"] == vc["credentialSubject"]["band"] and payload["id"] == p.id
    assert len(credential.verify_url(p.id, token)) < 900  # fits a QR code comfortably
    bad = token[:-6] + ("A" * 6 if not token.endswith("AAAAAA") else "B" * 6)
    assert not credential.read_qr_token(bad)[0]


def test_no_private_details_in_vc(db: Session) -> None:
    biz = strong_business(db)
    text = str(issue(db, biz, "test").vc_json)
    assert "phone" not in text and "CUSTOMER" not in text and "+91" not in text


def test_new_passport_supersedes_old(db: Session) -> None:
    biz = strong_business(db)
    first = issue(db, biz, "t")
    second = issue(db, biz, "t")
    assert first.status == "superseded" and second.status == "valid"


def test_api_status_verify_keys_pdf(client: TestClient) -> None:
    h, biz = setup_business(client)
    p = client.post(f"/businesses/{biz}/passport", headers=h).json()
    assert p["vc"]["credentialSubject"]["band"] == "U" and p["vc"]["credentialSubject"]["sandbox"]
    assert client.get(f"/passports/{p['id']}/status").json()["status"] == "valid"
    assert client.post("/passports/verify", json={"qr_token": p["qr_token"]}).json()[
        "signature_valid"
    ]
    forged = copy.deepcopy(p["vc"])
    forged["credentialSubject"]["band"] = "A"
    r = client.post("/passports/verify", json={"vc": forged}).json()
    assert r == {"signature_valid": False, "status": "unknown", "summary": {}}
    keys = client.get("/.well-known/ktp-keys.json").json()
    assert keys["keys"][0]["alg"] == "Ed25519"
    for lang, word in (("hi", "पासपोर्ट"), ("en", "Business Trust Passport")):
        r = client.get(f"/businesses/{biz}/passport.pdf?language={lang}", headers=h)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            txt = pdf.pages[0].extract_text() or ""
        assert "SANDBOX" in txt or "सैंडबॉक्स" in txt or lang == "hi"
        if lang == "en":
            assert word in txt


def test_hindi_html_has_devanagari_font() -> None:
    vc = {
        "credentialSubject": {
            "name": "शर्मा किराना",
            "category": "kirana",
            "city": "Indore",
            "band": "B",
            "pillars": {"money": 70.0},
            "rulesVersion": "r1",
            "sandbox": True,
        },
        "validUntil": "2027-01-01",
        "id": "x",
    }
    ex = {
        "band_label": "मज़बूत",
        "confidence_label": "ज़्यादा भरोसा",
        "status_label": "चालू",
        "headline": "आपका पासपोर्ट मज़बूत है।",
        "positives": [],
        "gaps": [],
        "improve": [],
    }
    out = render_html(vc, ex, "https://x/v/1#t", "hi")
    assert "noto-sans-devanagari-devanagari-400-normal.woff" in out and "शर्मा किराना" in out
