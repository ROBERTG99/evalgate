from pathlib import Path

import yaml


def test_action_contract(root: Path) -> None:
    action = yaml.safe_load((root / "action/action.yml").read_text())
    inputs = action["inputs"]
    assert inputs["suite"]["required"] is True
    defaults = {
        "report-md": "evalgate-report.md",
        "split": "test",
        "max-regression-pp": "1.0",
        "python-version": "3.13",
        "comment": "true",
    }
    for name, default in defaults.items():
        assert inputs[name]["default"] == default, name
    assert {"baseline", "extras"} <= set(inputs)
    assert set(action["outputs"]) == {"passed", "report-json", "check-json"}
    assert action["runs"]["using"] == "composite"
    text = (root / "action/action.yml").read_text()
    assert '"${ACTION_PATH}/.."' in text  # installs evalgate from the action's own checkout
    assert "pr_comment.py" in text
