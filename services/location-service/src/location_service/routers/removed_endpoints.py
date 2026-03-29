"""Exact 404 tombstones for removed Location Service endpoints."""

from fastapi import APIRouter

from location_service.errors import endpoint_removed

router = APIRouter(tags=["removed-endpoints"])


@router.post("/v1/pairs/{pair_id}/activate")
async def removed_activate_pair(pair_id: str) -> None:
    """Return an exact 404 for the removed pair activation endpoint."""
    del pair_id
    raise endpoint_removed()
