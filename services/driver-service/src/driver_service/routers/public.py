"""Public CRUD API router for Driver Service (spec §3.1–3.4).

Endpoints:
  POST   /api/v1/drivers              — create a new driver
  GET    /api/v1/drivers/{driver_id}   — fetch full driver detail
  GET    /api/v1/drivers               — list and search drivers
  PATCH  /api/v1/drivers/{driver_id}   — update mutable driver fields
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.auth import AuthContext, admin_auth_dependency, admin_or_manager_auth_dependency
from driver_service.database import get_session
from driver_service.enums import AuditActionType, DriverStatus, PhoneNormalizationStatus
from driver_service.errors import (
    driver_company_code_already_exists,
    driver_if_match_required,
    driver_internal_error,
    driver_not_found,
    driver_phone_already_exists,
    driver_telegram_already_exists,
    driver_validation_error,
    driver_version_mismatch,
)
from driver_service.models import DriverAuditLogModel, DriverModel, DriverOutboxModel
from driver_service.normalization import (
    build_full_name_search_key,
    etag_from_row_version,
    mask_phone_for_manager,
    normalize_phone,
    parse_if_match,
)
from driver_service.schemas import CreateDriverRequest, PatchDriverRequest
from driver_service.serializers import (
    serialize_driver_admin,
    serialize_driver_for_role,
    serialize_driver_list_item,
)

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/api/v1/drivers", tags=["drivers"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    return str(ULID())


async def _write_audit(
    session: AsyncSession,
    driver_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    *,
    changed_fields: dict[str, Any] | None = None,
    old_snapshot: dict[str, Any] | None = None,
    new_snapshot: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    """Write an audit log entry."""
    # PII Hardening: Mask sensitive fields in snapshots
    if old_snapshot and "phone" in old_snapshot:
        old_snapshot["phone"] = mask_phone_for_manager(old_snapshot["phone"])
    if new_snapshot and "phone" in new_snapshot:
        new_snapshot["phone"] = mask_phone_for_manager(new_snapshot["phone"])

    audit = DriverAuditLogModel(
        audit_id=_new_ulid(),
        driver_id=driver_id,
        action_type=action_type,
        changed_fields_json=json.dumps(changed_fields) if changed_fields else None,
        old_snapshot_json=json.dumps(old_snapshot) if old_snapshot else None,
        new_snapshot_json=json.dumps(new_snapshot) if new_snapshot else None,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        request_id=request_id,
        created_at_utc=_now_utc(),
    )
    session.add(audit)


async def _write_outbox(
    session: AsyncSession,
    driver_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> None:
    """Write an outbox row for reliable event publishing."""
    outbox = DriverOutboxModel(
        outbox_id=_new_ulid(),
        aggregate_type="DRIVER",
        aggregate_id=driver_id,
        aggregate_version=1,
        driver_id=driver_id,
        event_name=event_name,
        event_version=1,
        payload_json=json.dumps(payload),
        partition_key=driver_id,
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=_now_utc(),
        next_attempt_at_utc=_now_utc(),
    )
    session.add(outbox)


def _handle_integrity_error(exc: IntegrityError) -> None:
    """Parse IntegrityError to raise specific conflict errors."""
    detail = str(exc.orig) if exc.orig else str(exc)
    if "uq_driver_phone_e164_live" in detail:
        raise driver_phone_already_exists()
    if "uq_driver_telegram_user_id_live" in detail:
        raise driver_telegram_already_exists()
    if "uq_driver_company_code_live" in detail:
        raise driver_company_code_already_exists()
    raise driver_internal_error("Database constraint violation.")


# ---------------------------------------------------------------------------
# POST /api/v1/drivers — create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_driver(
    body: CreateDriverRequest,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new canonical driver record (spec §3.1)."""
    now = _now_utc()
    request_id = getattr(request.state, "request_id", None)

    # Phone normalization (manual create MUST reach NORMALIZED)
    phone_result = normalize_phone(body.phone)
    if phone_result.status != PhoneNormalizationStatus.NORMALIZED:
        raise driver_validation_error(
            "Phone number could not be normalized to a valid E.164 format.",
            errors=[{"field": "phone", "message": f"Normalization status: {phone_result.status.value}"}],
        )

    # Build search key
    search_key = build_full_name_search_key(body.full_name.strip())

    # Create driver record
    driver_id = _new_ulid()
    driver = DriverModel(
        driver_id=driver_id,
        company_driver_code=body.company_driver_code.strip() if body.company_driver_code else None,
        full_name=body.full_name.strip(),
        full_name_search_key=search_key,
        phone_raw=phone_result.phone_raw,
        phone_e164=phone_result.phone_e164,
        phone_normalization_status=phone_result.status.value,
        telegram_user_id=body.telegram_user_id.strip() if body.telegram_user_id else None,
        license_class=body.license_class.strip(),
        employment_start_date=body.employment_start_date,
        employment_end_date=None,
        status=DriverStatus.ACTIVE,
        inactive_reason=None,
        note=body.note,
        row_version=1,
        created_at_utc=now,
        created_by_actor_id=auth.actor_id,
        updated_at_utc=now,
        updated_by_actor_id=auth.actor_id,
    )
    session.add(driver)

    try:
        await session.flush()
        new_snapshot = serialize_driver_admin(driver)

        # Audit for CREATE
        await _write_audit(
            session,
            driver_id,
            AuditActionType.CREATE,
            auth.actor_id,
            auth.role,
            new_snapshot=new_snapshot,
            request_id=request_id,
        )
        await _write_outbox(
            session,
            driver_id,
            "driver.created.v1",
            {
                "driver_id": driver_id,
                "company_driver_code": driver.company_driver_code,
                "phone_e164": driver.phone_e164,
                "telegram_user_id": driver.telegram_user_id,
                "license_class": driver.license_class,
                "status": driver.status,
                "row_version": driver.row_version,
                "created_at_utc": now.isoformat(),
            },
        )
        await session.commit()
        from driver_service.observability import DRIVERS_CREATED_TOTAL, get_standard_labels

        labels = get_standard_labels()
        DRIVERS_CREATED_TOTAL.labels(**labels).inc()
    except IntegrityError as exc:
        await session.rollback()
        _handle_integrity_error(exc)
    except Exception as exc:
        await session.rollback()
        raise exc

    await session.refresh(driver)
    response.headers["ETag"] = etag_from_row_version(driver.row_version)
    return serialize_driver_for_role(driver, auth.role)


# ---------------------------------------------------------------------------
# GET /api/v1/drivers/{driver_id} — detail
# ---------------------------------------------------------------------------


@router.get("/{driver_id}")
async def get_driver(
    driver_id: str,
    response: Response,
    auth: AuthContext = Depends(admin_or_manager_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Fetch full driver detail (spec §3.2)."""
    result = await session.execute(select(DriverModel).where(DriverModel.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise driver_not_found(driver_id)

    response.headers["ETag"] = etag_from_row_version(driver.row_version)
    return serialize_driver_for_role(driver, auth.role)


# ---------------------------------------------------------------------------
# GET /api/v1/drivers — list
# ---------------------------------------------------------------------------


@router.get("")
async def list_drivers(
    auth: AuthContext = Depends(admin_or_manager_auth_dependency),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: str = Query("ACTIVE", pattern="^(ACTIVE|INACTIVE|IN_REVIEW|SUSPENDED|CANCELLED|ALL)$"),
    search: str | None = Query(None),
    telegram_state: str | None = Query(None, pattern="^(HAS_TELEGRAM|NO_TELEGRAM)$"),
    assignable_only: bool = Query(False),
    employment_start_from: str | None = Query(None),
    employment_start_to: str | None = Query(None),
    updated_from: str | None = Query(None),
    updated_to: str | None = Query(None),
    sort_by: str = Query("updated_at", pattern="^(full_name|created_at|updated_at|employment_start_date)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    """List and search drivers with pagination (spec §3.3)."""
    from driver_service.config import settings as cfg

    per_page = min(per_page, cfg.max_page_size)

    # Base query: Exclude CANCELLED by default unless searching for ALL or CANCELLED
    query: Select = select(DriverModel)  # type: ignore[type-arg]

    # Status filter
    if status == "ALL":
        # Usually we still want to hide CANCELLED unless explicitly requested
        pass
    else:
        query = query.where(DriverModel.status == status)

    if status != "CANCELLED" and status != "ALL":
        query = query.where(DriverModel.status != DriverStatus.CANCELLED)

    # Assignable filter
    if assignable_only:
        query = query.where(DriverModel.is_assignable.is_(True))

    # Telegram state filter
    if telegram_state == "HAS_TELEGRAM":
        query = query.where(DriverModel.telegram_user_id.is_not(None))
    elif telegram_state == "NO_TELEGRAM":
        query = query.where(DriverModel.telegram_user_id.is_(None))

    # Search: fuzzy on search_key, exact on phone/telegram/company_code
    if search:
        search_term = search.strip()
        search_key = build_full_name_search_key(search_term)
        query = query.where(
            or_(
                DriverModel.full_name_search_key.ilike(f"%{search_key}%"),
                DriverModel.phone_e164 == search_term,
                DriverModel.telegram_user_id == search_term,
                DriverModel.company_driver_code == search_term,
            )
        )

    # Date range filters
    if employment_start_from:
        query = query.where(DriverModel.employment_start_date >= employment_start_from)
    if employment_start_to:
        query = query.where(DriverModel.employment_start_date <= employment_start_to)
    if updated_from:
        query = query.where(DriverModel.updated_at_utc >= updated_from)
    if updated_to:
        query = query.where(DriverModel.updated_at_utc <= updated_to)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Sorting
    sort_col_map = {
        "full_name": DriverModel.full_name,
        "created_at": DriverModel.created_at_utc,
        "updated_at": DriverModel.updated_at_utc,
        "employment_start_date": DriverModel.employment_start_date,
    }
    sort_col = sort_col_map.get(sort_by, DriverModel.updated_at_utc)
    if sort_order == "desc":
        query = query.order_by(sort_col.desc(), DriverModel.driver_id.asc())
    else:
        query = query.order_by(sort_col.asc(), DriverModel.driver_id.asc())

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await session.execute(query)
    drivers = result.scalars().all()

    items = [serialize_driver_list_item(d, auth.role) for d in drivers]

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "items": items,
    }


# ---------------------------------------------------------------------------
# PATCH /api/v1/drivers/{driver_id} — update
# ---------------------------------------------------------------------------


@router.patch("/{driver_id}")
async def patch_driver(
    driver_id: str,
    body: PatchDriverRequest,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
    if_match: str | None = Header(None, alias="If-Match"),
) -> dict[str, Any]:
    """Update mutable driver fields (spec §3.4).

    Requires If-Match header for optimistic concurrency.
    employment_end_date does NOT change status (BR-09).
    """
    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    # Require If-Match
    expected_version = parse_if_match(if_match)
    if expected_version is None:
        raise driver_if_match_required()

    # Fetch driver
    result = await session.execute(select(DriverModel).where(DriverModel.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise driver_not_found(driver_id)

    # Version check
    if driver.row_version != expected_version:
        raise driver_version_mismatch()

    # Track old values for audit
    changed_fields: dict[str, list[Any]] = {}
    old_telegram = driver.telegram_user_id

    # Apply patch fields
    patch_data = body.model_dump(exclude_unset=True)

    if "full_name" in patch_data and patch_data["full_name"]:
        new_name = patch_data["full_name"].strip()
        if new_name != driver.full_name:
            changed_fields["full_name"] = [driver.full_name, new_name]
            driver.full_name = new_name
            driver.full_name_search_key = build_full_name_search_key(new_name)

    if "phone" in patch_data and patch_data["phone"]:
        phone_result = normalize_phone(patch_data["phone"])
        if phone_result.status != PhoneNormalizationStatus.NORMALIZED:
            raise driver_validation_error(
                "Phone number could not be normalized.",
                errors=[{"field": "phone", "message": f"Normalization status: {phone_result.status.value}"}],
            )
        if phone_result.phone_e164 != driver.phone_e164:
            changed_fields["phone_e164"] = [driver.phone_e164, phone_result.phone_e164]
            driver.phone_raw = phone_result.phone_raw
            driver.phone_e164 = phone_result.phone_e164
            driver.phone_normalization_status = phone_result.status.value

    if "telegram_user_id" in patch_data:
        new_tg = patch_data["telegram_user_id"]
        new_tg = new_tg.strip() if new_tg else None
        if new_tg != driver.telegram_user_id:
            changed_fields["telegram_user_id"] = [driver.telegram_user_id, new_tg]
            driver.telegram_user_id = new_tg

    if "company_driver_code" in patch_data:
        new_code = patch_data["company_driver_code"]
        new_code = new_code.strip() if new_code else None
        if new_code != driver.company_driver_code:
            changed_fields["company_driver_code"] = [driver.company_driver_code, new_code]
            driver.company_driver_code = new_code

    if "license_class" in patch_data and patch_data["license_class"]:
        new_lc = patch_data["license_class"].strip()
        if new_lc != driver.license_class:
            changed_fields["license_class"] = [driver.license_class, new_lc]
            driver.license_class = new_lc

    if "employment_start_date" in patch_data and patch_data["employment_start_date"]:
        if patch_data["employment_start_date"] != driver.employment_start_date:
            changed_fields["employment_start_date"] = [
                str(driver.employment_start_date),
                str(patch_data["employment_start_date"]),
            ]
            driver.employment_start_date = patch_data["employment_start_date"]

    if "employment_end_date" in patch_data:
        new_end = patch_data["employment_end_date"]
        if new_end != driver.employment_end_date:
            changed_fields["employment_end_date"] = [
                str(driver.employment_end_date) if driver.employment_end_date else None,
                str(new_end) if new_end else None,
            ]
            driver.employment_end_date = new_end

    if "note" in patch_data:
        if patch_data["note"] != driver.note:
            changed_fields["note"] = [driver.note, patch_data["note"]]
            driver.note = patch_data["note"]

    if not changed_fields:
        # No actual changes — return current state
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Validate employment dates
    if driver.employment_end_date and driver.employment_end_date < driver.employment_start_date:
        raise driver_validation_error(
            "employment_end_date must not be before employment_start_date.",
            errors=[{"field": "employment_end_date", "message": "Must be >= employment_start_date."}],
        )

    # Capture snapshots
    old_snapshot = serialize_driver_admin(driver)

    # Increment version
    driver.row_version += 1
    driver.updated_at_utc = now
    driver.updated_by_actor_id = auth.actor_id

    new_snapshot = serialize_driver_admin(driver)

    # Audit
    await _write_audit(
        session,
        driver_id,
        AuditActionType.UPDATE,
        auth.actor_id,
        auth.role,
        changed_fields=changed_fields,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        request_id=request_id,
    )

    # Outbox: driver.updated.v1
    await _write_outbox(
        session,
        driver_id,
        "driver.updated.v1",
        {
            "driver_id": driver_id,
            "changed_fields": list(changed_fields.keys()),
            "row_version": driver.row_version,
            "updated_at_utc": now.isoformat(),
        },
    )

    # Outbox: driver.telegram_changed.v1 (null→val, val→val, val→null)
    new_telegram = driver.telegram_user_id
    if "telegram_user_id" in changed_fields:
        await _write_outbox(
            session,
            driver_id,
            "driver.telegram_changed.v1",
            {
                "driver_id": driver_id,
                "old_telegram_user_id": old_telegram,
                "new_telegram_user_id": new_telegram,
                "row_version": driver.row_version,
                "updated_at_utc": now.isoformat(),
            },
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _handle_integrity_error(exc)

    await session.refresh(driver)
    response.headers["ETag"] = etag_from_row_version(driver.row_version)
    return serialize_driver_for_role(driver, auth.role)
