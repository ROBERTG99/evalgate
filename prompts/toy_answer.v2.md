# Toy answer prompt (v2)

Synthetic stand-in for a prompt. The toy target in `examples/toy-targets/src/toy_targets/systems.py`
implements this version with deterministic rules instead of a model call.

"Be brief": answers are capped at 70 characters. (Facts at the end of a sentence get cut. This version regresses.)
