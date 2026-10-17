# Toy extract prompt (v1)

Synthetic stand-in for a prompt. The toy target in `examples/toy-targets/src/toy_targets/systems.py`
implements this version with deterministic rules instead of a model call.

Return invoice_number, date (ISO 8601), total (number), currency (ISO 4217 code) and vendor.
