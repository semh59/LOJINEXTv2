"""Internal API router for Driver Service (spec §3.9–3.11).

Endpoints:
  GET   /internal/v1/drivers/{id}/resolve     — resolve driver for enrichment
  GET   /internal/v1/drivers/lookup           — exact match lookup
  POST  /internal/v1/drivers/eligibility/check — bulk eligibility check
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service.auth import AuthContext, internal_service_auth_dependency
from driver_service.database import get_session
from driver_service.errors import (
    driver_bulk_limit_exceeded,
    driver_lookup_ambiguous,
    driver_lookup_mode_invalid,
    driver_not_found,
)
from driver_service.models import DriverModel
from driver_service.normalization import derive_lifecycle_state
from driver_service.schemas import EligibilityCheckRequest

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/internal/v1/drivers", tags=["driver-internal"])


# ---------------------------------------------------------------------------
# GET /internal/v1/drivers/{driver_id}/resolve
# ---------------------------------------------------------------------------


@router.get("/{driver_id}/resolve")
async def resolve_driver(
    driver_id: str,
    auth: AuthContext = Depends(internal_service_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resolve driver for service-to-service enrichment (spec §3.9).

    Returns minimal fields needed by calling services.
    Includes soft-deleted for historical reference.
    """
    result = await session.execute(select(DriverModel).where(DriverModel.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise driver_not_found(driver_id)

    return {
        "driver_id": driver.driver_id,
        "company_driver_code": driver.company_driver_code,
        "full_name": driver.full_name,
        "phone_e164": driver.phone_e164,
        "telegram_user_id": driver.telegram_user_id,
        "license_class": driver.license_class,
        "status": driver.status,
        "lifecycle_state": derive_lifecycle_state(driver.status, driver.soft_deleted_at_utc),
        "is_assignable": driver.is_assignable,
    }


# ---------------------------------------------------------------------------
# GET /internal/v1/drivers/lookup
# ---------------------------------------------------------------------------


@router.get("/lookup")
async def lookup_driver(
    auth: AuthContext = Depends(internal_service_auth_dependency),
    session: AsyncSession = Depends(get_session),
    phone_e164: str | None = Query(None),
    telegram_user_id: str | None = Query(None),
    company_driver_code: str | None = Query(None),
) -> dict:
    """Exact-match driver lookup (spec §3.10).

    Exactly ONE lookup key must be provided.
    If ambiguous (>1 match): 409 DRIVER_LOOKUP_AMBIGUOUS.
    Only searches live (non-soft-deleted) drivers.
    """
    keys_provided = sum(1 for k in [phone_e164, telegram_user_id, company_driver_code] if k is not None)
    if keys_provided != 1:
        raise driver_lookup_mode_invalid()

    query = select(DriverModel).where(DriverModel.soft_deleted_at_utc.is_(None))

    if phone_e164:
        query = query.where(DriverModel.phone_e164 == phone_e164)
    elif telegram_user_id:
        query = query.where(DriverModel.telegram_user_id == telegram_user_id)
    elif company_driver_code:
        query = query.where(DriverModel.company_driver_code == company_driver_code)

    result = await session.execute(query)
    drivers = result.scalars().all()

    if len(drivers) == 0:
        raise driver_not_found()
    if len(drivers) > 1:
        raise driver_lookup_ambiguous()

    driver = drivers[0]
    return {
        "driver_id": driver.driver_id,
        "company_driver_code": driver.company_driver_code,
        "full_name": driver.full_name,
        "phone_e164": driver.phone_e164,
        "telegram_user_id": driver.telegram_user_id,
        "license_class": driver.license_class,
        "status": driver.status,
        "lifecycle_state": derive_lifecycle_state(driver.status, driver.soft_deleted_at_utc),
        "is_assignable": driver.is_assignable,
    }


# ---------------------------------------------------------------------------
# POST /internal/v1/drivers/eligibility/check
# ---------------------------------------------------------------------------

MAX_ELIGIBILITY_IDS = 200


@router.post("/eligibility/check")
async def check_eligibility(
    body: EligibilityCheckRequest,
    auth: AuthContext = Depends(internal_service_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Bulk eligibility check for driver IDs (spec §3.11).

    Max 200 IDs per request. Returns existence, status, and assignability for each ID.
    """
    if len(body.driver_ids) > MAX_ELIGIBILITY_IDS:
        raise driver_bulk_limit_exceeded(MAX_ELIGIBILITY_IDS)

    if not body.driver_ids:
        return {"items": []}

    # De-duplicate IDs
    unique_ids = list(dict.fromkeys(body.driver_ids))

    result = await session.execute(select(DriverModel).where(DriverModel.driver_id.in_(unique_ids)))
    found_drivers = {d.driver_id: d for d in result.scalars().all()}

    items: list[dict] = []
    for driver_id in unique_ids:
        driver = found_drivers.get(driver_id)
        if driver:
            items.append(
                {
                    "driver_id": driver_id,
                    "exists": True,
                    "status": driver.status,
                    "lifecycle_state": derive_lifecycle_state(driver.status, driver.soft_deleted_at_utc),
                    "has_telegram": driver.telegram_user_id is not None,
                    "is_assignable": driver.is_assignable,
                }
            )
        else:
            items.append(
                {
                    "driver_id": driver_id,
                    "exists": False,
                    "status": None,
                    "lifecycle_state": None,
                    "has_telegram": False,
                    "is_assignable": False,
                }
            )

    return {"items": items}
