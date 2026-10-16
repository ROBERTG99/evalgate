import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import eval_live  # noqa: E402
from tests.judge_helpers import Scripted, verdict  # noqa: E402

CRIT = {"states_key_facts": "met", "no_contradiction": "met", "answers_question": "met"}


def test_refuses_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "live.json"
    assert eval_live.run(provider_name="anthropic", out=out) == 2
    data = json.loads(out.read_text())
    assert data["ran"] is False
    assert "ANTHROPIC_API_KEY" in data["reason"]


def test_stops_at_budget(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "live.json"
    provider = Scripted(always=verdict("pass", 1.0, CRIT))
    # The estimate for 64 items x 4 calls on claude-haiku-5-5 is about USD 0.07: a USD 0.05 budget stops first.
    code = eval_live.run(provider_name="anthropic", provider=provider, out=out, budget_usd=0.05)
    assert code == 3
    assert provider.calls == 0  # stopped before any provider call
    assert "live estimate" in capsys.readouterr().err
    assert json.loads(out.read_text())["stopped_at_budget"] is True


def test_hard_stop_during_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "live.json"
    provider = Scripted(always=verdict("pass", 1.0, CRIT))
    monkeypatch.setattr(eval_live, "plan", lambda n, model: eval_live.estimate_judge_cost(0, [(model, 0)]))
    code = eval_live.run(provider_name="anthropic", provider=provider, out=out, budget_usd=0.001)
    assert code == 3
    assert 0 < provider.calls < 256  # the spend guard stopped the run part-way


def test_live_run_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "live.json"
    provider = Scripted(always=verdict("pass", 1.0, CRIT))
    code = eval_live.run(provider_name="anthropic", provider=provider, out=out, budget_usd=2.0)
    data: dict[str, Any] = json.loads(out.read_text())
    assert data["ran"] is True and data["mode"] == "live"
    assert data["cost_usd"] > 0
    assert code == 1  # an always-pass judge must fail calibration
    assert data["calibration"]["passed"] is False
