"""SQLAlchemy models for identity-service."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Identity Service models."""


class IdentityUserModel(Base):
    """User account."""

    __tablename__ = "identity_users"

    user_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IdentityGroupModel(Base):
    """Named authorization group."""

    __tablename__ = "identity_groups"

    group_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    group_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdentityUserGroupModel(Base):
    """User-to-group join table."""

    __tablename__ = "identity_user_groups"

    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("identity_groups.group_id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IdentityPermissionModel(Base):
    """Canonical permission dictionary."""

    __tablename__ = "identity_permissions"

    permission_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdentityGroupPermissionModel(Base):
    """Group-to-permission join table."""

    __tablename__ = "identity_group_permissions"

    group_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("identity_groups.group_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_key: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("identity_permissions.permission_key", ondelete="CASCADE"),
        primary_key=True,
    )


class IdentityRefreshTokenModel(Base):
    """Stored refresh tokens (hashed)."""

    __tablename__ = "identity_refresh_tokens"

    token_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("identity_users.user_id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("idx_identity_refresh_user", "user_id", "expires_at_utc"),)


class IdentitySigningKeyModel(Base):
    """Persisted signing keys."""

    __tablename__ = "identity_signing_keys"

    kid: Mapped[str] = mapped_column(String(64), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_ciphertext_b64: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_kek_version: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    retired_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IdentityServiceClientModel(Base):
    """Service clients allowed to mint internal service tokens."""

    __tablename__ = "identity_service_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    rotated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IdentityOutboxModel(Base):
    """Transactional outbox for reliable event publishing."""

    __tablename__ = "identity_outbox"

    outbox_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="USER"
    )
    aggregate_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(nullable=False, default=1)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    publish_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING"
    )
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    next_attempt_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claim_expires_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_identity_outbox_aggregate",
            "aggregate_type",
            "aggregate_id",
            "created_at_utc",
        ),
        Index(
            "idx_identity_outbox_pending",
            "publish_status",
            "next_attempt_at_utc",
            "created_at_utc",
        ),
    )


class IdentityAuditLogModel(Base):
    """Deep audit log for identity mutations."""

    __tablename__ = "identity_audit_log"

    audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    target_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # USER, GROUP, etc.
    target_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("identity_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    old_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_identity_audit_target_created",
            "target_type",
            "target_id",
            "created_at_utc",
        ),
    )


class IdentityWorkerHeartbeatModel(Base):
    """Worker heartbeat rows used by readiness probes."""

    __tablename__ = "identity_worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
