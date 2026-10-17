import subprocess
import sys

import evalgate
from evalgate import testing


def test_public_api() -> None:
    assert evalgate.__version__ == "0.1.0"
    for name in ["metric", "Case", "MetricScore", "StepRecord", "TargetResult", "Metric"]:
        assert getattr(evalgate, name) is not None
    for name in ["Cassette", "FakeJudge", "FakeLLM", "CassetteMismatch"]:
        assert hasattr(testing, name)


def test_import_is_light() -> None:
    code = "import sys, evalgate; print(sorted(m for m in ('numpy','duckdb','httpx','anthropic','openai') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
