"""Schemathesis property tests against the toy-targets OpenAPI schema (in-process ASGI, no sockets)."""

import schemathesis
from hypothesis import HealthCheck, settings

from toy_targets.app import create_app

schema = schemathesis.openapi.from_asgi("/openapi.json", create_app())


@schema.parametrize()
@settings(max_examples=25, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
def test_api_conforms(case: schemathesis.Case) -> None:
    # Catalogued variants model regressions and deliberately break the response contract
    # (e.g. a dropped field), so conformance is checked on the released versions v1 and v2.
    if case.headers:
        case.headers.pop("x-toy-variant", None)
        case.headers.pop("X-Toy-Variant", None)
    case.call_and_validate()
