# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/ROBERTG99/evalgate/security/advisories/new) for this repository. Do not open a public issue. Include the affected version or commit, steps to reproduce and the impact you expect.

You can expect an acknowledgement within 5 working days and a fix or mitigation plan within 30 days for confirmed issues. Fixed issues are listed in [`CHANGELOG.md`](CHANGELOG.md) once a release ships.

## Scope

In scope: the `evalgate` package, its CLI, the report viewer, the GitHub Action in `action/`, the Docker images and the workflows in `.github/workflows/`.

Out of scope: the toy targets in `examples/` (test fixtures), the synthetic data, and findings that require a malicious suite file (suites are trusted configuration that can run Python code by design).

The threat model, controls and scan results are in [`docs/security.md`](docs/security.md).
