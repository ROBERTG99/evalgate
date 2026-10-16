import json
import subprocess
import sys
from pathlib import Path

import pytest

from evalgate.judge.calibrate import calibrate, cohen_kappa, confusion

ROOT = Path(__file__).resolve().parents[3]


def test_kappa_reference_matrix() -> None:
    # Hand-computed 2x2 example: confusion [[20, 5], [10, 15]] (rows = label, columns = judge).
    # po = 35/50 = 0.7; pe = (25/50)(30/50) + (25/50)(20/50) = 0.5; kappa = (0.7 - 0.5) / (1 - 0.5) = 0.4
    labels = ["1"] * 25 + ["0"] * 25
    preds = ["1"] * 20 + ["0"] * 5 + ["1"] * 10 + ["0"] * 15
    assert abs(cohen_kappa(labels, preds) - 0.4) < 1e-9
    assert confusion(labels, preds) == {"0": {"0": 15, "1": 10}, "1": {"0": 5, "1": 20}}
    assert cohen_kappa(["a", "a"], ["a", "a"]) == 1.0
    assert cohen_kappa([], []) == 0.0


def _labels(tmp_path: Path, n_good: int, n_bad: int, flip: int) -> Path:
    rows = []
    for i in range(n_good + n_bad):
        good = i < n_good
        label = 1 if good else 0
        if i < flip:  # labelled pass but the candidate contradicts the reference: judge disagrees
            label = 1
        cand = "Refunds arrive within 5 business days." if good else "Refunds arrive within 9 business days."
        if i < flip:
            cand = "Refunds arrive within 9 business days."
        rows.append(
            {
                "id": f"l{i}",
                "rubric": "answer_correctness",
                "split": "test",
                "input": "How long?",
                "reference": "Refunds arrive within 5 business days.",
                "candidate": cand,
                "candidate_b": None,
                "label": label,
                "source": "construction",
                "meta": {"construction": "t"},
            }
        )
    path = tmp_path / "labels.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def run_cli(labels: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "evalgate.cli",
            "calibrate",
            "--rubric",
            "evals/rubrics/answer_correctness.v1.yaml",
            "--labels",
            str(labels),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_exit_1_below_threshold(tmp_path: Path) -> None:
    labels = _labels(tmp_path, 40, 40, flip=20)  # 80 test items, 20 disagreements: agreement 0.75
    proc = run_cli(labels)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL" in proc.stdout


def test_exit_0_at_threshold(tmp_path: Path) -> None:
    labels = _labels(tmp_path, 40, 40, flip=0)  # 80 test items, all agree
    proc = run_cli(labels)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "agreement 1.000" in proc.stdout


def test_real_labels_meet_thresholds() -> None:
    result = calibrate(
        ROOT / "evals/rubrics/answer_correctness.v1.yaml",
        ROOT / "evals/datasets/judge/answer_correctness.labels.v1.jsonl",
    )
    assert result["passed"], result["checks"]
    assert result["injection_items"] == 8
    assert result["injection_pass_through"] == 0.0
    assert result["n"] + 16 == 80  # 64 pointwise + 16 pairwise test items


def test_no_labels_for_rubric_is_invalid(tmp_path: Path) -> None:
    from evalgate.errors import InvalidInputError

    labels = _labels(tmp_path, 2, 2, 0)
    with pytest.raises(InvalidInputError, match="no dev labels"):
        calibrate(ROOT / "evals/rubrics/answer_correctness.v1.yaml", labels, split="dev")
