from pathlib import Path

from app.detection.rules import auth_anomalous_source_success, auth_failed_burst, blocked_observable, process_suspicious_child  # noqa: F401
from app.detection.sigma import load_pack as _load_sigma_pack

_load_sigma_pack(Path(__file__).parent / "sigma_pack")
