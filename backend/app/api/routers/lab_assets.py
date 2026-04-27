from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.errors import ErrorEnvelope
from app.api.schemas.responses import LabAssetIn, LabAssetOut
from app.auth.dependencies import SystemUser, require_analyst, require_user, resolve_actor_id
from app.auth.models import User
from app.db.models import LabAsset
from app.db.session import get_db

router = APIRouter(prefix="/lab/assets", tags=["lab"])


@router.get("", response_model=list[LabAssetOut])
async def list_lab_assets(
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
) -> list[LabAssetOut]:
    result = await db.execute(select(LabAsset).order_by(LabAsset.kind, LabAsset.natural_key))
    return [
        LabAssetOut(
            id=a.id,
            kind=a.kind.value,
            natural_key=a.natural_key,
            registered_at=a.registered_at,
            notes=a.notes,
        )
        for a in result.scalars().all()
    ]


@router.post("", response_model=LabAssetOut, status_code=201, responses={409: {"model": ErrorEnvelope}})
async def register_lab_asset(
    body: LabAssetIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> LabAssetOut:
    existing = await db.scalar(
        select(LabAsset.id).where(
            LabAsset.kind == body.kind,
            LabAsset.natural_key == body.natural_key,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "asset_exists", "message": f"{body.kind.value}:{body.natural_key} is already registered"}},
        )
    actor_id = await resolve_actor_id(current_user, db)
    asset = LabAsset(
        id=uuid.uuid4(),
        kind=body.kind,
        natural_key=body.natural_key,
        notes=body.notes,
        created_by_user_id=actor_id,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return LabAssetOut(
        id=asset.id,
        kind=asset.kind.value,
        natural_key=asset.natural_key,
        registered_at=asset.registered_at,
        notes=asset.notes,
    )


@router.delete("/{asset_id}", status_code=204, responses={404: {"model": ErrorEnvelope}})
async def deregister_lab_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_analyst),
) -> None:
    asset = await db.get(LabAsset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "asset_not_found", "message": "Lab asset not found"}},
        )
    await db.delete(asset)
    await db.commit()
