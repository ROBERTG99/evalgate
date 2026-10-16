# Toy classify prompt (v1)

Synthetic stand-in for a prompt. The toy target in `examples/toy-targets/src/toy_targets/systems.py`
implements this version with deterministic rules instead of a model call.

Classify the support ticket into one of: account_access, cancellation, feature_request, billing,
shipping, bug_report. Check the categories in that order and pick the first that matches.
