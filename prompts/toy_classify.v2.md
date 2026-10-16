# Toy classify prompt (v2)

Synthetic stand-in for a prompt. The toy target in `examples/toy-targets/src/toy_targets/systems.py`
implements this version with deterministic rules instead of a model call.

Shorter prompt: classify into cancellation, feature_request, billing, shipping or bug_report.
(The account-access instructions were cut. This version regresses.)
