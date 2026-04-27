from __future__ import annotations

from fastapi import APIRouter

from app.attack.catalog import AttackCatalog, get_catalog

router = APIRouter(prefix="/attack", tags=["attack"])


@router.get("/catalog", response_model=AttackCatalog)
def get_attack_catalog() -> AttackCatalog:
    return get_catalog()
