"""fix column length drift: align migration schema to model definitions

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-04-07

Context:
  Baseline migration (a1b2c3d4e5f6) defined ULID reference columns as
  String(50) and actor_type columns as String(20). The audit log migration
  (d1e2f3a4b5c6) defined actor_id as String(64). The SQLAlchemy models
  correctly define all ULID columns as String(26), actor_type/role as
  String(32). This corrective migration aligns the database to the model.

  All downsizes (50→26, 64→26) are safe: ULIDs are exactly 26 characters;
  no existing value can exceed the new limit. All upsizes (20→32) are
  always safe (column expansion).
"""

import sqlalchemy as sa

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # trip_trips — ULID reference columns: String(50) → String(26)
    op.alter_column("trip_trips", "driver_id", existing_type=sa.String(50), type_=sa.String(26), nullable=True)
    op.alter_column("trip_trips", "vehicle_id", existing_type=sa.String(50), type_=sa.String(26), nullable=True)
    op.alter_column("trip_trips", "trailer_id", existing_type=sa.String(50), type_=sa.String(26), nullable=True)
    op.alter_column("trip_trips", "route_pair_id", existing_type=sa.String(50), type_=sa.String(26), nullable=True)
    op.alter_column("trip_trips", "route_id", existing_type=sa.String(50), type_=sa.String(26), nullable=True)
    op.alter_column("trip_trips", "created_by_actor_id", existing_type=sa.String(50), type_=sa.String(26), nullable=False)

    # trip_trips — actor_type: String(20) → String(32)
    op.alter_column("trip_trips", "created_by_actor_type", existing_type=sa.String(20), type_=sa.String(32), nullable=False)

    # trip_trip_timeline — actor_id: String(50) → String(26)
    op.alter_column("trip_trip_timeline", "actor_id", existing_type=sa.String(50), type_=sa.String(26), nullable=False)

    # trip_trip_timeline — actor_type: String(20) → String(32)
    op.alter_column("trip_trip_timeline", "actor_type", existing_type=sa.String(20), type_=sa.String(32), nullable=False)

    # trip_trip_delete_audit — actor_id: String(64) → String(26)
    op.alter_column("trip_trip_delete_audit", "actor_id", existing_type=sa.String(64), type_=sa.String(26), nullable=False)


def downgrade() -> None:
    # Reverse: expand columns back to their pre-migration sizes
    op.alter_column("trip_trips", "driver_id", existing_type=sa.String(26), type_=sa.String(50), nullable=True)
    op.alter_column("trip_trips", "vehicle_id", existing_type=sa.String(26), type_=sa.String(50), nullable=True)
    op.alter_column("trip_trips", "trailer_id", existing_type=sa.String(26), type_=sa.String(50), nullable=True)
    op.alter_column("trip_trips", "route_pair_id", existing_type=sa.String(26), type_=sa.String(50), nullable=True)
    op.alter_column("trip_trips", "route_id", existing_type=sa.String(26), type_=sa.String(50), nullable=True)
    op.alter_column("trip_trips", "created_by_actor_id", existing_type=sa.String(26), type_=sa.String(50), nullable=False)
    op.alter_column("trip_trips", "created_by_actor_type", existing_type=sa.String(32), type_=sa.String(20), nullable=False)
    op.alter_column("trip_trip_timeline", "actor_id", existing_type=sa.String(26), type_=sa.String(50), nullable=False)
    op.alter_column("trip_trip_timeline", "actor_type", existing_type=sa.String(32), type_=sa.String(20), nullable=False)
    op.alter_column("trip_trip_delete_audit", "actor_id", existing_type=sa.String(26), type_=sa.String(64), nullable=False)
