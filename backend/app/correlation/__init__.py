# Import order is correlator REGISTRATION ORDER. The engine returns the first
# non-None result from `run_correlators`, so the correlator that should "win"
# when multiple match must come first.
#
# identity_endpoint_chain MUST run before endpoint_compromise_join: both can
# match a process event when an open identity_compromise exists for the user,
# but only the chain produces the critical cross-layer incident the kill-chain
# UI is built around. If join wins, we silently lose the chain.
#
# Do not let isort/ruff alphabetize these imports.
# isort: skip_file
# fmt: off
from app.correlation.rules import identity_compromise  # noqa: F401, I001
from app.correlation.rules import identity_endpoint_chain  # noqa: F401, I001
from app.correlation.rules import endpoint_compromise_join  # noqa: F401, I001
from app.correlation.rules import endpoint_compromise_standalone  # noqa: F401, I001
# fmt: on
