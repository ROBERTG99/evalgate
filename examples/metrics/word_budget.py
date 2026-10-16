"""Example custom metric: 1.0 when an answer stays within a word budget, decaying linearly above it.

Use it from a suite with ``plugins: [examples.metrics.word_budget]`` and
``{name: brevity, kind: custom, params: {metric: word_budget, field: answer, max_words: 40}}``.
"""

from __future__ import annotations

from typing import Any

import evalgate
from evalgate.contracts import Case, TargetResult


@evalgate.metric("word_budget")
def word_budget(case: Case, result: TargetResult, params: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    field = str(params.get("field", "answer"))
    limit = int(params.get("max_words", 40))
    output = result.output
    text = output.get(field, "") if isinstance(output, dict) else str(output)
    n = len(str(text).split())
    value = 1.0 if n <= limit else max(0.0, 1.0 - (n - limit) / limit)
    return value, {"words": n, "max_words": limit}
