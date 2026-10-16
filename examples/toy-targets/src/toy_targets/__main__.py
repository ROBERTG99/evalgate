"""Run the toy targets: ``toy-targets --host 127.0.0.1 --port 8110``."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="evalgate toy targets")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8110)
    args = parser.parse_args()
    uvicorn.run("toy_targets.app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
