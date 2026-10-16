"""Environment configuration. Every ``EVALGATE_*`` variable is read here."""

from __future__ import annotations

import os
from pathlib import Path


def env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def home() -> Path:
    return Path(env_str("EVALGATE_HOME", ".evalgate"))


def bootstrap_seed() -> int:
    return env_int("EVALGATE_BOOTSTRAP_SEED", 1337)


def case_timeout_s() -> float:
    return env_float("EVALGATE_CASE_TIMEOUT_S", 60.0)


def run_timeout_s() -> float:
    return env_float("EVALGATE_RUN_TIMEOUT_S", 1800.0)


def target_retries() -> int:
    return max(0, env_int("EVALGATE_TARGET_RETRIES", 2))


def judge_concurrency() -> int:
    return max(1, env_int("EVALGATE_JUDGE_CONCURRENCY", 4))


def judge_timeout_s() -> float:
    return env_float("EVALGATE_JUDGE_TIMEOUT_S", 60.0)


def http_allowed_hosts() -> set[str]:
    raw = env_str("EVALGATE_HTTP_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,toy-targets")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def llm_provider() -> str:
    return env_str("EVALGATE_LLM_PROVIDER", "fake").lower()


def judge_model() -> str:
    return env_str("EVALGATE_JUDGE_MODEL", "claude-haiku-5-5")


def judge_hard_model() -> str:
    return env_str("EVALGATE_JUDGE_HARD_MODEL", "claude-opus-5-5")


def cache_ttl_days() -> int:
    return env_int("EVALGATE_CACHE_TTL_DAYS", 90)


def live_budget_usd() -> float:
    return env_float("LIVE_EVAL_BUDGET_USD", 2.0)


def serve_token() -> str:
    return os.environ.get("EVALGATE_SERVE_TOKEN", "").strip()


def is_live() -> bool:
    return llm_provider() != "fake"


def serve_allowed_hosts() -> set[str]:
    """Extra Host header names the viewer accepts (for example a compose service name)."""
    raw = os.environ.get("EVALGATE_SERVE_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}
