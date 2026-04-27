"""Dump the FastAPI OpenAPI schema to backend/openapi.json.

Usage (from repo root):
    docker compose exec backend python -m scripts.dump_openapi

Or directly:
    cd backend && python -m scripts.dump_openapi
"""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    from app.main import app  # noqa: PLC0415  import inside main to avoid import-time side effects

    schema = app.openapi()
    out = Path(__file__).parent.parent / "openapi.json"
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"OpenAPI schema written to {out}")


if __name__ == "__main__":
    main()
