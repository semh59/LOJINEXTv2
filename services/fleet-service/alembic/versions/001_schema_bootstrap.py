"""Fleet Service schema bootstrap — 9 tables, 17+ indexes, btree_gist extension.

Revision ID: 001_schema_bootstrap
Revises: -
Create Date: 2026-04-02

Source: FLEET_SERVICE_PLAN_v1_5_PRODUCTION_FINAL.md Sections 8.2–8.10
"""

from alembic import op

# revision identifiers
revision = "001_schema_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all Fleet Service tables, indexes, and constraints."""

    # ── btree_gist extension (mandatory for exclusion constraints) ──
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    # Verify btree_gist is available (fail-fast in CI)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist') THEN
                RAISE EXCEPTION 'btree_gist extension is required but not installed';
            END IF;
        END $$;
    """)

    # ── 8.2 fleet_vehicles ──
    op.execute("""
        CREATE TABLE fleet_vehicles (
            vehicle_id                  CHAR(26)     PRIMARY KEY,
            asset_code                  VARCHAR(50)  NOT NULL,
            plate_raw_current           VARCHAR(32)  NOT NULL,
            normalized_plate_current    VARCHAR(32)  NOT NULL,
            brand                       VARCHAR(80)  NULL,
            model                       VARCHAR(80)  NULL,
            model_year                  SMALLINT     NULL
                CHECK (model_year IS NULL OR model_year BETWEEN 1950 AND 2100),
            ownership_type              VARCHAR(20)  NOT NULL
                CHECK (ownership_type IN ('OWNED','LEASED','THIRD_PARTY')),
            status                      VARCHAR(16)  NOT NULL
                CHECK (status IN ('ACTIVE','INACTIVE')),
            notes                       TEXT         NULL,
            row_version                 BIGINT       NOT NULL DEFAULT 1
                CHECK (row_version > 0),
            spec_stream_version         BIGINT       NOT NULL DEFAULT 0
                CHECK (spec_stream_version >= 0),
            is_selectable               BOOLEAN      GENERATED ALWAYS AS (
                                            status = 'ACTIVE' AND soft_deleted_at_utc IS NULL
                                        ) STORED,
            created_at_utc              TIMESTAMPTZ  NOT NULL,
            created_by_actor_type       VARCHAR(20)  NOT NULL
                CHECK (created_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            created_by_actor_id         VARCHAR(64)  NOT NULL,
            updated_at_utc              TIMESTAMPTZ  NOT NULL,
            updated_by_actor_type       VARCHAR(20)  NOT NULL
                CHECK (updated_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            updated_by_actor_id         VARCHAR(64)  NOT NULL,
            soft_deleted_at_utc         TIMESTAMPTZ  NULL,
            soft_deleted_by_actor_type  VARCHAR(20)  NULL
                CHECK (soft_deleted_by_actor_type IS NULL OR
                       soft_deleted_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            soft_deleted_by_actor_id    VARCHAR(64)  NULL,
            soft_delete_reason          TEXT         NULL,

            CONSTRAINT chk_fleet_vehicles_soft_delete_coherence CHECK (
                (soft_deleted_at_utc IS NULL AND soft_deleted_by_actor_type IS NULL
                    AND soft_deleted_by_actor_id IS NULL AND soft_delete_reason IS NULL)
                OR
                (soft_deleted_at_utc IS NOT NULL AND soft_deleted_by_actor_type IS NOT NULL
                    AND soft_deleted_by_actor_id IS NOT NULL AND soft_delete_reason IS NOT NULL)
            )
        );
    """)

    # Vehicle indexes
    op.execute("CREATE UNIQUE INDEX ux_fleet_vehicles_asset_code ON fleet_vehicles (asset_code);")
    op.execute("""
        CREATE UNIQUE INDEX ux_fleet_vehicles_plate_live
            ON fleet_vehicles (normalized_plate_current)
            WHERE soft_deleted_at_utc IS NULL;
    """)
    op.execute("""
        CREATE INDEX ix_fleet_vehicles_status_updated
            ON fleet_vehicles (status, updated_at_utc DESC, vehicle_id DESC);
    """)
    op.execute("""
        CREATE INDEX ix_fleet_vehicles_created
            ON fleet_vehicles (created_at_utc DESC, vehicle_id DESC);
    """)
    op.execute("""
        CREATE INDEX ix_fleet_vehicles_soft_deleted_at
            ON fleet_vehicles (soft_deleted_at_utc)
            WHERE soft_deleted_at_utc IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX ix_fleet_vehicles_selectable
            ON fleet_vehicles (is_selectable, normalized_plate_current, vehicle_id)
            WHERE is_selectable = TRUE;
    """)

    # ── 8.3 fleet_trailers ──
    op.execute("""
        CREATE TABLE fleet_trailers (
            trailer_id                  CHAR(26)     PRIMARY KEY,
            asset_code                  VARCHAR(50)  NOT NULL,
            plate_raw_current           VARCHAR(32)  NOT NULL,
            normalized_plate_current    VARCHAR(32)  NOT NULL,
            brand                       VARCHAR(80)  NULL,
            model                       VARCHAR(80)  NULL,
            model_year                  SMALLINT     NULL
                CHECK (model_year IS NULL OR model_year BETWEEN 1950 AND 2100),
            ownership_type              VARCHAR(20)  NOT NULL
                CHECK (ownership_type IN ('OWNED','LEASED','THIRD_PARTY')),
            status                      VARCHAR(16)  NOT NULL
                CHECK (status IN ('ACTIVE','INACTIVE')),
            notes                       TEXT         NULL,
            row_version                 BIGINT       NOT NULL DEFAULT 1
                CHECK (row_version > 0),
            spec_stream_version         BIGINT       NOT NULL DEFAULT 0
                CHECK (spec_stream_version >= 0),
            is_selectable               BOOLEAN      GENERATED ALWAYS AS (
                                            status = 'ACTIVE' AND soft_deleted_at_utc IS NULL
                                        ) STORED,
            created_at_utc              TIMESTAMPTZ  NOT NULL,
            created_by_actor_type       VARCHAR(20)  NOT NULL
                CHECK (created_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            created_by_actor_id         VARCHAR(64)  NOT NULL,
            updated_at_utc              TIMESTAMPTZ  NOT NULL,
            updated_by_actor_type       VARCHAR(20)  NOT NULL
                CHECK (updated_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            updated_by_actor_id         VARCHAR(64)  NOT NULL,
            soft_deleted_at_utc         TIMESTAMPTZ  NULL,
            soft_deleted_by_actor_type  VARCHAR(20)  NULL
                CHECK (soft_deleted_by_actor_type IS NULL OR
                       soft_deleted_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            soft_deleted_by_actor_id    VARCHAR(64)  NULL,
            soft_delete_reason          TEXT         NULL,

            CONSTRAINT chk_fleet_trailers_soft_delete_coherence CHECK (
                (soft_deleted_at_utc IS NULL AND soft_deleted_by_actor_type IS NULL
                    AND soft_deleted_by_actor_id IS NULL AND soft_delete_reason IS NULL)
                OR
                (soft_deleted_at_utc IS NOT NULL AND soft_deleted_by_actor_type IS NOT NULL
                    AND soft_deleted_by_actor_id IS NOT NULL AND soft_delete_reason IS NOT NULL)
            )
        );
    """)

    # Trailer indexes
    op.execute("CREATE UNIQUE INDEX ux_fleet_trailers_asset_code ON fleet_trailers (asset_code);")
    op.execute("""
        CREATE UNIQUE INDEX ux_fleet_trailers_plate_live
            ON fleet_trailers (normalized_plate_current)
            WHERE soft_deleted_at_utc IS NULL;
    """)
    op.execute("""
        CREATE INDEX ix_fleet_trailers_status_updated
            ON fleet_trailers (status, updated_at_utc DESC, trailer_id DESC);
    """)
    op.execute("""
        CREATE INDEX ix_fleet_trailers_created
            ON fleet_trailers (created_at_utc DESC, trailer_id DESC);
    """)
    op.execute("""
        CREATE INDEX ix_fleet_trailers_soft_deleted_at
            ON fleet_trailers (soft_deleted_at_utc)
            WHERE soft_deleted_at_utc IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX ix_fleet_trailers_selectable
            ON fleet_trailers (is_selectable, normalized_plate_current, trailer_id)
            WHERE is_selectable = TRUE;
    """)

    # ── 8.4 fleet_vehicle_spec_versions ──
    op.execute("""
        CREATE TABLE fleet_vehicle_spec_versions (
            vehicle_spec_version_id  CHAR(26)      PRIMARY KEY,
            vehicle_id               CHAR(26)      NOT NULL
                REFERENCES fleet_vehicles(vehicle_id) ON DELETE RESTRICT,
            version_no               INTEGER       NOT NULL CHECK (version_no > 0),
            effective_from_utc       TIMESTAMPTZ   NOT NULL,
            effective_to_utc         TIMESTAMPTZ   NULL,
            is_current               BOOLEAN       NOT NULL,
            fuel_type                VARCHAR(16)   NULL
                CHECK (fuel_type IN ('DIESEL','LNG','CNG','ELECTRIC','HYBRID','OTHER')),
            powertrain_type          VARCHAR(20)   NULL
                CHECK (powertrain_type IN ('ICE','BEV','PHEV','HEV','FCEV','OTHER')),
            engine_power_kw          NUMERIC(8,2)  NULL CHECK (engine_power_kw > 0),
            engine_displacement_l    NUMERIC(6,2)  NULL CHECK (engine_displacement_l > 0),
            emission_class           VARCHAR(16)   NULL
                CHECK (emission_class IN ('EURO_3','EURO_4','EURO_5','EURO_6','OTHER')),
            transmission_type        VARCHAR(16)   NULL
                CHECK (transmission_type IN ('MANUAL','AUTOMATED_MANUAL','AUTOMATIC','OTHER')),
            gear_count               SMALLINT      NULL CHECK (gear_count BETWEEN 1 AND 24),
            final_drive_ratio        NUMERIC(6,3)  NULL CHECK (final_drive_ratio > 0),
            axle_config              VARCHAR(8)    NULL
                CHECK (axle_config IN ('4X2','6X2','6X4','8X2','8X4','OTHER')),
            total_axle_count         SMALLINT      NULL CHECK (total_axle_count BETWEEN 1 AND 6),
            driven_axle_count        SMALLINT      NULL CHECK (driven_axle_count BETWEEN 1 AND 4),
            curb_weight_kg           NUMERIC(10,2) NULL CHECK (curb_weight_kg > 0),
            gvwr_kg                  NUMERIC(10,2) NULL CHECK (gvwr_kg > 0),
            gcwr_kg                  NUMERIC(10,2) NULL CHECK (gcwr_kg > 0),
            payload_capacity_kg      NUMERIC(10,2) NULL CHECK (payload_capacity_kg >= 0),
            tractor_cab_type         VARCHAR(16)   NULL
                CHECK (tractor_cab_type IN ('DAY','SLEEPER','OTHER')),
            roof_height_class        VARCHAR(16)   NULL
                CHECK (roof_height_class IN ('LOW','MEDIUM','HIGH','OTHER')),
            aero_package_level       VARCHAR(16)   NULL
                CHECK (aero_package_level IN ('NONE','LOW','MEDIUM','HIGH')),
            tire_rr_class            VARCHAR(16)   NULL
                CHECK (tire_rr_class IN ('UNKNOWN','STANDARD','LOW_RR','ULTRA_LOW_RR')),
            tire_type                VARCHAR(16)   NULL
                CHECK (tire_type IN ('STANDARD','WIDE_BASE','OTHER')),
            speed_limiter_kph        SMALLINT      NULL CHECK (speed_limiter_kph BETWEEN 20 AND 180),
            pto_present              BOOLEAN       NULL,
            apu_present              BOOLEAN       NULL,
            idle_reduction_type      VARCHAR(16)   NULL
                CHECK (idle_reduction_type IN ('NONE','APU','BATTERY_AC','AUTO_START_STOP','OTHER')),
            first_registration_date  DATE          NULL,
            in_service_date          DATE          NULL,
            change_reason            TEXT          NOT NULL,
            created_at_utc           TIMESTAMPTZ   NOT NULL,
            created_by_actor_type    VARCHAR(20)   NOT NULL
                CHECK (created_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            created_by_actor_id      VARCHAR(64)   NOT NULL,

            CONSTRAINT chk_fleet_vspec_window CHECK (
                effective_to_utc IS NULL OR effective_to_utc > effective_from_utc
            ),
            CONSTRAINT chk_fleet_vspec_axle_consistency CHECK (
                driven_axle_count IS NULL OR total_axle_count IS NULL
                OR driven_axle_count <= total_axle_count
            )
        );
    """)

    # Vehicle spec indexes + exclusion constraint
    op.execute("""
        CREATE UNIQUE INDEX ux_fleet_vehicle_spec_no
            ON fleet_vehicle_spec_versions (vehicle_id, version_no);
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_fleet_vehicle_spec_current
            ON fleet_vehicle_spec_versions (vehicle_id)
            WHERE is_current = TRUE;
    """)
    op.execute("""
        CREATE INDEX ix_fleet_vehicle_spec_asof
            ON fleet_vehicle_spec_versions (vehicle_id, effective_from_utc DESC, effective_to_utc);
    """)
    op.execute("""
        ALTER TABLE fleet_vehicle_spec_versions
            ADD CONSTRAINT excl_fleet_vehicle_spec_no_overlap
            EXCLUDE USING gist (
                vehicle_id WITH =,
                tstzrange(effective_from_utc, COALESCE(effective_to_utc, 'infinity'::timestamptz)) WITH &&
            );
    """)

    # ── 8.5 fleet_trailer_spec_versions ──
    op.execute("""
        CREATE TABLE fleet_trailer_spec_versions (
            trailer_spec_version_id  CHAR(26)      PRIMARY KEY,
            trailer_id               CHAR(26)      NOT NULL
                REFERENCES fleet_trailers(trailer_id) ON DELETE RESTRICT,
            version_no               INTEGER       NOT NULL CHECK (version_no > 0),
            effective_from_utc       TIMESTAMPTZ   NOT NULL,
            effective_to_utc         TIMESTAMPTZ   NULL,
            is_current               BOOLEAN       NOT NULL,
            trailer_type             VARCHAR(24)   NULL
                CHECK (trailer_type IN (
                    'DRY_VAN','REEFER','TANKER','FLATBED',
                    'CURTAIN','TIPPER','CONTAINER_CHASSIS','OTHER'
                )),
            body_type                VARCHAR(24)   NULL
                CHECK (body_type IN ('BOX','TANK','OPEN','CURTAIN','OTHER')),
            tare_weight_kg           NUMERIC(10,2) NULL CHECK (tare_weight_kg > 0),
            max_payload_kg           NUMERIC(10,2) NULL CHECK (max_payload_kg >= 0),
            axle_count               SMALLINT      NULL CHECK (axle_count BETWEEN 1 AND 8),
            lift_axle_present        BOOLEAN       NULL,
            body_height_mm           INTEGER       NULL CHECK (body_height_mm > 0),
            body_length_mm           INTEGER       NULL CHECK (body_length_mm > 0),
            body_width_mm            INTEGER       NULL CHECK (body_width_mm > 0),
            tire_rr_class            VARCHAR(16)   NULL
                CHECK (tire_rr_class IN ('UNKNOWN','STANDARD','LOW_RR','ULTRA_LOW_RR')),
            tire_type                VARCHAR(16)   NULL
                CHECK (tire_type IN ('STANDARD','WIDE_BASE','OTHER')),
            side_skirts_present      BOOLEAN       NULL,
            rear_tail_present        BOOLEAN       NULL,
            gap_reducer_present      BOOLEAN       NULL,
            wheel_covers_present     BOOLEAN       NULL,
            reefer_unit_present      BOOLEAN       NULL,
            reefer_unit_type         VARCHAR(24)   NULL
                CHECK (reefer_unit_type IN ('DIESEL','ELECTRIC','HYBRID','OTHER')),
            reefer_power_source      VARCHAR(24)   NULL
                CHECK (reefer_power_source IN ('SELF_POWERED','TRACTOR_POWERED','GRID_CHARGED','OTHER')),
            aero_package_level       VARCHAR(16)   NULL
                CHECK (aero_package_level IN ('NONE','LOW','MEDIUM','HIGH')),
            change_reason            TEXT          NOT NULL,
            created_at_utc           TIMESTAMPTZ   NOT NULL,
            created_by_actor_type    VARCHAR(20)   NOT NULL
                CHECK (created_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            created_by_actor_id      VARCHAR(64)   NOT NULL,

            CONSTRAINT chk_fleet_tspec_window CHECK (
                effective_to_utc IS NULL OR effective_to_utc > effective_from_utc
            )
        );
    """)

    # Trailer spec indexes + exclusion constraint
    op.execute("""
        CREATE UNIQUE INDEX ux_fleet_trailer_spec_no
            ON fleet_trailer_spec_versions (trailer_id, version_no);
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_fleet_trailer_spec_current
            ON fleet_trailer_spec_versions (trailer_id)
            WHERE is_current = TRUE;
    """)
    op.execute("""
        CREATE INDEX ix_fleet_trailer_spec_asof
            ON fleet_trailer_spec_versions (trailer_id, effective_from_utc DESC, effective_to_utc);
    """)
    op.execute("""
        ALTER TABLE fleet_trailer_spec_versions
            ADD CONSTRAINT excl_fleet_trailer_spec_no_overlap
            EXCLUDE USING gist (
                trailer_id WITH =,
                tstzrange(effective_from_utc, COALESCE(effective_to_utc, 'infinity'::timestamptz)) WITH &&
            );
    """)

    # ── 8.6 fleet_asset_timeline_events ──
    op.execute("""
        CREATE TABLE fleet_asset_timeline_events (
            event_id         CHAR(26)     PRIMARY KEY,
            aggregate_type   VARCHAR(16)  NOT NULL
                CHECK (aggregate_type IN ('VEHICLE','TRAILER')),
            aggregate_id     CHAR(26)     NOT NULL,
            event_type       VARCHAR(64)  NOT NULL,
            actor_type       VARCHAR(20)  NOT NULL
                CHECK (actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            actor_id         VARCHAR(64)  NOT NULL,
            request_id       VARCHAR(64)  NULL,
            correlation_id   VARCHAR(64)  NULL,
            occurred_at_utc  TIMESTAMPTZ  NOT NULL,
            payload_json     JSONB        NOT NULL
        );
    """)
    op.execute("""
        CREATE INDEX ix_fleet_timeline_aggregate_time
            ON fleet_asset_timeline_events (aggregate_type, aggregate_id, occurred_at_utc DESC);
    """)

    # ── 8.7 fleet_asset_delete_audit ──
    op.execute("""
        CREATE TABLE fleet_asset_delete_audit (
            delete_audit_id                   CHAR(26)      PRIMARY KEY,
            aggregate_type                    VARCHAR(16)   NOT NULL
                CHECK (aggregate_type IN ('VEHICLE','TRAILER')),
            aggregate_id                      CHAR(26)      NOT NULL,
            snapshot_json                     JSONB         NOT NULL,
            reference_check_json              JSONB         NULL,
            reference_check_status            VARCHAR(32)   NOT NULL
                CHECK (reference_check_status IN ('NOT_ATTEMPTED','SUCCEEDED','DEPENDENCY_UNAVAILABLE')),
            delete_attempted_by_actor_type    VARCHAR(20)   NOT NULL
                CHECK (delete_attempted_by_actor_type IN ('ADMIN','SUPER_ADMIN','SERVICE','SYSTEM')),
            delete_attempted_by_actor_id      VARCHAR(64)   NOT NULL,
            delete_result                     VARCHAR(64)   NOT NULL
                CHECK (delete_result IN (
                    'REJECTED_UNAUTHORIZED',
                    'REJECTED_NOT_FOUND',
                    'REJECTED_ETAG_MISMATCH',
                    'REJECTED_NOT_SOFT_DELETED',
                    'REJECTED_DEPENDENCY_UNAVAILABLE',
                    'REJECTED_REFERENCED',
                    'SUCCEEDED'
                )),
            delete_result_reason              VARCHAR(256)  NOT NULL,
            created_at_utc                    TIMESTAMPTZ   NOT NULL
        );
    """)
    op.execute("""
        CREATE INDEX ix_fleet_delete_audit_aggregate
            ON fleet_asset_delete_audit (aggregate_id, created_at_utc DESC);
    """)

    # ── 8.8 fleet_outbox ──
    op.execute("""
        CREATE TABLE fleet_outbox (
            outbox_id           CHAR(26)     PRIMARY KEY,
            aggregate_type      VARCHAR(16)  NOT NULL
                CHECK (aggregate_type IN ('VEHICLE','TRAILER')),
            aggregate_id        CHAR(26)     NOT NULL,
            event_name          VARCHAR(80)  NOT NULL,
            event_version       INTEGER      NOT NULL CHECK (event_version > 0),
            payload_json        JSONB        NOT NULL,
            publish_status      VARCHAR(16)  NOT NULL
                CHECK (publish_status IN ('PENDING','PUBLISHED','FAILED','DEAD_LETTER')),
            attempt_count       INTEGER      NOT NULL DEFAULT 0
                CHECK (attempt_count >= 0),
            last_error_code     VARCHAR(64)  NULL,
            last_error_message  TEXT         NULL,
            next_attempt_at_utc TIMESTAMPTZ  NOT NULL,
            created_at_utc      TIMESTAMPTZ  NOT NULL,
            published_at_utc    TIMESTAMPTZ  NULL
        );
    """)
    op.execute("""
        CREATE INDEX ix_fleet_outbox_worker_poll
            ON fleet_outbox (publish_status, next_attempt_at_utc, created_at_utc)
            WHERE publish_status IN ('PENDING', 'FAILED');
    """)
    op.execute("""
        CREATE INDEX ix_fleet_outbox_aggregate_status
            ON fleet_outbox (aggregate_id, publish_status)
            WHERE publish_status IN ('PENDING', 'FAILED');
    """)

    # ── 8.9 fleet_idempotency_records ──
    op.execute("""
        CREATE TABLE fleet_idempotency_records (
            idempotency_key       VARCHAR(128)  NOT NULL,
            endpoint_fingerprint  VARCHAR(64)   NOT NULL,
            request_hash          VARCHAR(64)   NOT NULL,
            response_status_code  INTEGER       NOT NULL,
            response_body_json    JSONB         NOT NULL,
            resource_type         VARCHAR(16)   NOT NULL
                CHECK (resource_type IN ('VEHICLE','TRAILER')),
            resource_id           CHAR(26)      NOT NULL,
            created_at_utc        TIMESTAMPTZ   NOT NULL,
            expires_at_utc        TIMESTAMPTZ   NOT NULL,

            PRIMARY KEY (idempotency_key, endpoint_fingerprint)
        );
    """)
    op.execute("""
        CREATE INDEX ix_fleet_idempotency_expires
            ON fleet_idempotency_records (expires_at_utc)
            WHERE expires_at_utc IS NOT NULL;
    """)

    # ── 8.10 fleet_worker_heartbeats ──
    op.execute("""
        CREATE TABLE fleet_worker_heartbeats (
            worker_name      VARCHAR(64)  PRIMARY KEY,
            recorded_at_utc  TIMESTAMPTZ  NOT NULL,
            details_json     JSONB        NULL
        );
    """)
    op.execute("""
        CREATE INDEX ix_fleet_worker_heartbeats_recorded
            ON fleet_worker_heartbeats (recorded_at_utc DESC);
    """)


def downgrade() -> None:
    """Drop all Fleet Service tables in reverse dependency order."""
    op.execute("DROP TABLE IF EXISTS fleet_worker_heartbeats CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_idempotency_records CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_outbox CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_asset_delete_audit CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_asset_timeline_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_trailer_spec_versions CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_vehicle_spec_versions CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_trailers CASCADE;")
    op.execute("DROP TABLE IF EXISTS fleet_vehicles CASCADE;")
