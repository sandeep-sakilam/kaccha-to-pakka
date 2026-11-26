import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

from app.adapters.ai import MockAI
from app.adapters.gateway import AIGateway
from app.modules.trust.explain import T, explain

REASONS = {
    "positives": [
        {"code": "ledger_matches", "params": {"percent": 82}},
        {"code": "partners_confirmed", "params": {"count": 3}},
    ],
    "gaps": [{"code": "money_data_old", "params": {"days": 40}}],
    "improve": [{"code": "ask_partners", "params": {"more": 2}}],
}


class LLM(MockAI):
    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines

    def generate(self, system: str, prompt: str, language: str) -> str:
        return json.dumps(self.lines, ensure_ascii=False)


def test_template_headline_matches_spec() -> None:
    e = explain("B", "High", "final", REASONS, "en")
    assert e.headline == (
        "Your passport is strong because 82% of your ledger matches your bank "
        "payments and 3 trading partners confirmed you."
    )
    assert e.improve == ["Ask 2 more suppliers or customers to confirm"] and e.source == "template"


def test_hindi_templates() -> None:
    e = explain("B", "High", "final", REASONS, "hi")
    assert "82%" in e.positives[0] and e.band_label == "मज़बूत" and "क्योंकि" in e.headline


def test_mock_llm_echo_falls_back_to_template() -> None:
    e = explain("B", "High", "final", REASONS, "hi", AIGateway(MockAI()))
    assert e.source == "template"


def test_good_llm_output_is_used() -> None:
    lines = [
        "बहुत बढ़िया: आपके खाते का 82% बैंक से मिलता है",
        "3 साथियों ने हाँ कहा",
        "बैंक डेटा 40 दिन पुराना है",
        "2 और साथियों से पूछिए",
    ]
    e = explain("B", "High", "final", REASONS, "hi", AIGateway(LLM(lines)))
    assert e.source == "llm" and e.positives[0].startswith("बहुत बढ़िया")


def test_llm_that_changes_a_number_or_adds_a_reason_is_rejected() -> None:
    changed = ["95% matches", "3 confirmed", "40 days", "2 more"]
    assert (
        explain("B", "High", "final", REASONS, "en", AIGateway(LLM(changed))).source == "template"
    )
    extra = ["82% matches", "3 confirmed", "40 days", "2 more", "You will surely get a loan"]
    assert explain("B", "High", "final", REASONS, "en", AIGateway(LLM(extra))).source == "template"


def test_llm_down_uses_template() -> None:
    e = explain("B", "High", "final", REASONS, "en", AIGateway(MockAI(fail=True)))
    assert e.source == "template"


def test_on_hold_headline_and_unverified() -> None:
    assert "on hold" in explain("B", "High", "on_hold", REASONS, "en").headline
    assert (
        explain(
            "U", "Low", "final", {"gaps": [{"code": "no_money_data", "params": {}}]}, "en"
        ).band_label
        == "Insufficient evidence"
    )


def test_every_reason_code_has_both_languages() -> None:
    from app.modules.trust import rules

    src = Path(rules.__file__).read_text()
    import re

    codes = set(re.findall(r'Reason\("([a-z_0-9]+)"', src))
    assert codes <= set(T), codes - set(T)
    assert all({"en", "hi"} <= set(v) for v in T.values())


def test_api(client: "TestClient") -> None:
    from tests.conftest import setup_business

    h, biz = setup_business(client)
    assert client.get(f"/businesses/{biz}/explanation", headers=h).status_code == 404
    client.post(f"/businesses/{biz}/assess", headers=h)
    e = client.get(f"/businesses/{biz}/explanation?language=en", headers=h).json()
    assert e["band"] == "U" and e["band_label"] == "Insufficient evidence"
    assert "Link your bank account" in e["improve"]
