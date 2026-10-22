---
name: demo-capture
description: Capture evalgate's viewer screenshots with Playwright into docs/images/ and the scripted demo transcript. Use after viewer changes and before updating the README.
---

# Demo capture

Screenshots and the demo transcript are real outputs of commands, never mocked or edited images.

## Steps

1. Start the stack and seed it:

   ```bash
   make up      # docker compose up -d --build --wait, then make seed
   ```

   Without Docker, run the toy targets and `evalgate serve <reports-dir> --port 8100` on the host, seeded by `./scripts/seed.sh`. Check `curl -fsS http://127.0.0.1:8100/healthz`.
2. Capture screenshots and run axe:

   ```bash
   EVALGATE_VIEWER_URL=http://127.0.0.1:8100 make e2e
   ```

   `tests/e2e/test_viewer.py` writes `docs/images/runs-list.png`, `run-detail-dark.png`, `compare-regression.png`, `mobile-375.png` and `demo.webm`. On Claude Code on the web use the preinstalled Chromium (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); never run `playwright install`.
3. Open each image with the Read tool and check it shows real data, the right theme and width, and no error page.
4. Record the demo transcript:

   ```bash
   ./scripts/demo.sh 2>&1 | tee docs/demo-transcript.txt
   ```

   (or `make demo`). It must show the v2 check failing with exit 1, then exit 0 after switching to v1.
5. Run `uv run pytest tests/integration/test_demo.py -q` to confirm the scripted scenario still holds.
6. Reference the images and transcript from `README.md` with relative links; numbers shown in captions cite their report.
7. Stop the stack with `make down`, and note the commands and results in the pull request.
