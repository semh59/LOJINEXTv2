"""Response serializers for role-based field visibility (spec §3.2, BR-16, BR-17)."""

from __future__ import annotations

from typing import Any

from driver_service.enums import ActorRole
from driver_service.models import DriverModel
from driver_service.normalization import mask_phone_for_manager


def serialize_driver_admin(driver: DriverModel, *, mask_pii: bool = False) -> dict[str, Any]:
    """Full driver resource for ADMIN callers."""
    phone = driver.phone_e164
    if mask_pii and phone and len(phone) > 7:
        # Example: +905321234567 -> +90532***567
        phone = phone[:7] + "***" + phone[-3:]

    return {
        "driver_id": driver.driver_id,
        "company_driver_code": driver.company_driver_code,
        "full_name": driver.full_name,
        "phone": phone,
        "phone_normalization_status": driver.phone_normalization_status,
        "telegram_user_id": driver.telegram_user_id,
        "license_class": driver.license_class,
        "employment_start_date": driver.employment_start_date.isoformat() if driver.employment_start_date else None,
        "employment_end_date": driver.employment_end_date.isoformat() if driver.employment_end_date else None,
        "status": driver.status,
        "is_assignable": driver.is_assignable,
        "note": driver.note,
        "row_version": driver.row_version,
        "created_at_utc": driver.created_at_utc.isoformat() if driver.created_at_utc else None,
        "updated_at_utc": driver.updated_at_utc.isoformat() if driver.updated_at_utc else None,
    }


def serialize_driver_manager(driver: DriverModel) -> dict[str, Any]:
    """Driver resource for MANAGER — phone masked, note/normalization_status omitted."""
    return {
        "driver_id": driver.driver_id,
        "company_driver_code": driver.company_driver_code,
        "full_name": driver.full_name,
        "phone": mask_phone_for_manager(driver.phone_e164),
        "telegram_user_id": driver.telegram_user_id,
        "license_class": driver.license_class,
        "employment_start_date": driver.employment_start_date.isoformat() if driver.employment_start_date else None,
        "employment_end_date": driver.employment_end_date.isoformat() if driver.employment_end_date else None,
        "status": driver.status,
        "is_assignable": driver.is_assignable,
        "row_version": driver.row_version,
        "updated_at_utc": driver.updated_at_utc.isoformat() if driver.updated_at_utc else None,
    }


def serialize_driver_internal(driver: DriverModel) -> dict[str, Any]:
    """Driver resource for INTERNAL_SERVICE — minimal fields."""
    return {
        "driver_id": driver.driver_id,
        "company_driver_code": driver.company_driver_code,
        "full_name": driver.full_name,
        "telegram_user_id": driver.telegram_user_id,
        "license_class": driver.license_class,
        "status": driver.status,
        "is_assignable": driver.is_assignable,
    }


def serialize_driver_for_role(driver: DriverModel, role: str) -> dict[str, Any]:
    """Serialize a driver resource based on the caller's role."""
    if role == ActorRole.ADMIN:
        return serialize_driver_admin(driver)
    if role == ActorRole.MANAGER:
        return serialize_driver_manager(driver)
    return serialize_driver_internal(driver)


def serialize_driver_list_item(driver: DriverModel, role: str) -> dict[str, Any]:
    """Serialize a driver for list responses — uses MANAGER shape by default, ADMIN gets full."""
    if role == ActorRole.ADMIN:
        return serialize_driver_admin(driver)
    return serialize_driver_manager(driver)
