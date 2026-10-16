SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV ?= uv
RUN := $(UV) run --frozen
TOOLS := $(CURDIR)/.tools/bin
export PATH := $(TOOLS):$(PATH)
export EVALGATE_BOOTSTRAP_SEED ?= 1337
COMPOSE := docker compose
COMPOSE_TEST := docker compose -f compose.test.yaml
CORE_PKGS := suite runner targets metrics judge stats cache store report

.PHONY: help bootstrap up down seed demo logs check-fast test test-docker e2e eval eval-live bench \
	lint typecheck security verify verify-clean docs clean seed-data meta-eval calibrate \
	record-fixtures test-extras schemas build sbom tools fmt coverage

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-16s %s\n", $$1, $$2}'

bootstrap: ## Install toolchains and dependencies, create .env from .env.example
	@test -f .env || cp .env.example .env
	$(UV) sync --frozen --all-extras
	./scripts/install_tools.sh

tools: ## Install pinned CLI tools into .tools/bin
	./scripts/install_tools.sh

up: ## Start the stack with healthchecks and seed the viewer
	$(COMPOSE) up -d --build --wait
	$(MAKE) seed

down: ## Stop the stack
	$(COMPOSE) down

seed: ## Load the synthetic runs (seed 1337) into the viewer
	./scripts/seed.sh

demo: ## Scripted demo against the running stack, offline
	./scripts/demo.sh

logs: ## Follow the logs of every service
	$(COMPOSE) logs -f

fmt: ## Format Python code
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

check-fast: ## Ruff and unit tests (< 60 s)
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) pytest tests/unit tests/harness -x -m "not slow"

test: ## Unit, integration, contract tests and simulations on the host
	$(RUN) pytest tests/unit tests/integration tests/contract tests/harness \
		--cov=evalgate --cov-report=term --cov-report=json:.evalgate/coverage.json
	$(RUN) python scripts/check_coverage.py .evalgate/coverage.json

coverage: test ## Alias of test (coverage gates included)

test-docker: ## The full test suite inside containers (adds E2E and promtool)
	./scripts/test_docker.sh

e2e: ## Playwright and axe against the running viewer (EVALGATE_VIEWER_URL)
	$(RUN) pytest tests/e2e -m e2e --force-enable-socket

eval: ## Offline evals with thresholds, writes evals/REPORT.md
	$(RUN) python scripts/run_evals.py
	$(MAKE) calibrate
	$(MAKE) meta-eval
	$(RUN) python scripts/build_eval_report.py --check

eval-live: ## Live evals with real models within LIVE_EVAL_BUDGET_USD
	$(RUN) python scripts/eval_live.py

bench: ## Performance tests with budgets
	$(RUN) python scripts/bench.py

lint: ## Ruff, markdownlint, shellcheck, hadolint, actionlint
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	./scripts/lint_tools.sh

typecheck: ## mypy --strict on src/
	$(RUN) mypy --strict src/evalgate

security: ## gitleaks, bandit, pip-audit, licenses, trivy
	./scripts/security.sh

schemas: ## Export JSON Schemas and fail on drift
	$(RUN) python scripts/export_schemas.py --check

build: ## Wheel and sdist, 1 MB budget
	rm -rf dist
	$(UV) build --package evalgate --out-dir dist
	$(RUN) python scripts/check_wheel.py dist

sbom: ## Write dist/sbom.cdx.json
	@mkdir -p dist
	$(RUN) cyclonedx-py environment --of JSON -o dist/sbom.cdx.json .venv

seed-data: ## Regenerate datasets (seed 1337) and check MANIFEST.json
	$(RUN) python -m data.generator --check

meta-eval: ## Run the 50-variant meta-evaluation
	$(RUN) python scripts/meta_eval.py

calibrate: ## Calibrate every rubric on its test labels
	$(RUN) python scripts/calibrate_all.py

record-fixtures: ## Record cassettes during live evals
	EVALGATE_RECORD_CASSETTES=1 $(RUN) python scripts/eval_live.py

test-extras: ## Tests of the optional extras (ragas, deepeval, langgraph, otel)
	$(RUN) pytest tests -m extras

verify: ## lint, typecheck, security, test, eval, bench and build
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) schemas
	$(MAKE) security
	$(MAKE) test
	$(MAKE) test-extras
	$(MAKE) eval
	$(MAKE) bench
	$(MAKE) build

verify-clean: ## make verify in a fresh clone in a temporary folder
	./scripts/verify_clean.sh

docs: ## Regenerate schemas, OpenAPI, contract docs and screenshots
	$(RUN) python scripts/export_schemas.py
	$(RUN) python scripts/export_openapi.py
	$(MAKE) e2e

clean: ## Remove containers, volumes, caches and build outputs
	-$(COMPOSE) down -v --remove-orphans
	-$(COMPOSE_TEST) down -v --remove-orphans
	rm -rf dist build .evalgate .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov .coverage
