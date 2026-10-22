"""Exceptions that carry the CLI exit code."""

from __future__ import annotations

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_INVALID_INPUT = 2
EXIT_BUDGET_ABORT = 3
EXIT_INTERNAL = 4
EXIT_STRICT_EXPORT = 5


class EvalgateError(Exception):
    """Base error; ``exit_code`` is used by the CLI."""

    exit_code = EXIT_INTERNAL


class InvalidInputError(EvalgateError):
    """A suite, dataset, rubric, label file or report failed validation."""

    exit_code = EXIT_INVALID_INPUT

    def __init__(self, path: str, location: str, problem: str) -> None:
        self.path = path
        self.location = location
        self.problem = problem
        where = f"{path}:{location}" if location else path
        super().__init__(f"{where}: {problem}")


class BudgetAbortError(EvalgateError):
    """A live run would exceed, or has exceeded, ``LIVE_EVAL_BUDGET_USD``."""

    exit_code = EXIT_BUDGET_ABORT


class StrictExportError(EvalgateError):
    """An exporter failed while ``--strict`` was set."""

    exit_code = EXIT_STRICT_EXPORT


class JudgeUnavailableError(EvalgateError):
    """The judge provider kept failing after retries; the gate fails closed."""


class CassetteMismatchError(EvalgateError):
    """A cassette exists for the key but its ``request_digest`` does not match the request."""


# Public alias.
CassetteMismatch = CassetteMismatchError
