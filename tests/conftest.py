import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("LANGSMITH_TRACING", "false")


@pytest.fixture(scope="session")
def toys_url() -> Iterator[str]:
    from tests.toy_server import toy_server

    with toy_server() as url:
        yield url
