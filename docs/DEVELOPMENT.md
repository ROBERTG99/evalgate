# Development

## Environment detected at bootstrap (2026-10-16)

| Item | Value |
|---|---|
| Mode | Claude Code on the web (`CLAUDE_CODE_REMOTE=true`) |
| `uname -srm` | Linux 6.18.44-fc-v139 x86_64 |
| python3 | 3.13.16 |
| uv | 0.11.32 |
| node | v22.22.0 |
| pnpm | 10.28.0 |
| go | go1.24.7 |
| docker | 29.8.2 |
| docker compose | 5.6.0 |
| gh | 2.89.0 |

Docker: the daemon is preinstalled but not running in the cloud container; it is started with the
registry mirror `mirror.gcr.io` (Appendix A of the build spec, automated by `.claude/hooks/session_start.sh`).

