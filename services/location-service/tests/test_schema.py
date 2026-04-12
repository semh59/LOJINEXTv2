import pytest
from sqlalchemy import select

from location_service.models import LocationPoint, Route, RoutePair


@pytest.mark.asyncio
async def test_schema_importable() -> None:
    """Basic test to ensure all models are importable and represent the schema."""
    assert LocationPoint.__tablename__ == "location_points"
    assert RoutePair.__tablename__ == "location_route_pairs"
    assert Route.__tablename__ == "location_routes"

    # Just verifying that the models can be referenced
    stmt = select(LocationPoint).limit(1)
    assert stmt is not None
