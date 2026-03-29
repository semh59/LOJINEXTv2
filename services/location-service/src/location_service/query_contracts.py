"""Helpers for public pagination and sort contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import asc, desc

from location_service.errors import request_validation_error

_ALLOWED_DIRECTIONS = {"asc", "desc"}


@dataclass(frozen=True)
class PaginationContract:
    """Resolved pagination parameters for public list endpoints."""

    page: int
    per_page: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


@dataclass(frozen=True)
class SortContract:
    """Resolved sort token for public list endpoints."""

    token: str
    field: str
    direction: str


def _validation(field: str, message: str) -> Exception:
    return request_validation_error([
        {"field": field, "message": message, "type": "value_error"},
    ])


def resolve_pagination(
    *,
    page: int,
    per_page: int | None,
    limit: int | None,
    default_per_page: int = 20,
    max_per_page: int = 100,
) -> PaginationContract:
    """Resolve canonical per_page with deprecated limit compatibility."""
    effective = per_page if per_page is not None else limit
    if effective is None:
        effective = default_per_page
    if effective < 1 or effective > max_per_page:
        raise _validation("query.per_page", f"per_page must be between 1 and {max_per_page}.")
    return PaginationContract(page=page, per_page=effective)


def resolve_sort(*, sort: str | None, allowed: set[str], default: str) -> SortContract:
    """Validate a public sort token and return its parsed shape."""
    token = (sort or default).strip()
    if token not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise _validation("query.sort", f"sort must be one of: {allowed_values}.")
    field, direction = token.split(":", 1)
    if direction not in _ALLOWED_DIRECTIONS:
        raise _validation("query.sort", "sort direction must be asc or desc.")
    return SortContract(token=token, field=field, direction=direction)


def build_order_by(sort_contract: SortContract, field_mapping: Mapping[str, Any]) -> Any:
    """Build a SQLAlchemy order-by clause from a validated sort contract."""
    column = field_mapping.get(sort_contract.field)
    if column is None:
        allowed_fields = ", ".join(sorted(field_mapping))
        raise _validation("query.sort", f"Unsupported sort field. Allowed fields: {allowed_fields}.")
    return asc(column) if sort_contract.direction == "asc" else desc(column)
