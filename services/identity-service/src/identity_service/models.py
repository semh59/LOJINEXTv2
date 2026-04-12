"""Database models for Identity Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class IdentityUserModel(Base):
    __tablename__ = "identity_users"

    user_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deactivated_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IdentityGroupModel(Base):
    __tablename__ = "identity_groups"

    group_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    group_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)


class IdentityPermissionModel(Base):
    __tablename__ = "identity_permissions"

    permission_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)


class IdentityUserGroupModel(Base):
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
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdentityGroupPermissionModel(Base):
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


class IdentitySigningKeyModel(Base):
    __tablename__ = "identity_signing_keys"

    kid: Mapped[str] = mapped_column(String(64), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text(), nullable=False)
    private_key_ciphertext_b64: Mapped[str] = mapped_column(Text(), nullable=False)
    private_key_kek_version: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_identity_signing_keys_active", "is_active", "created_at_utc"),)


class IdentityServiceClientModel(Base):
    __tablename__ = "identity_service_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    client_secret_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IdentityAuditLogModel(Base):
    __tablename__ = "identity_audit_log"

    audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    old_snapshot_json: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    new_snapshot_json: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_identity_audit_log_target", "target_type", "target_id", "created_at_utc"),
        Index("ix_identity_audit_log_actor", "actor_id", "created_at_utc"),
        Index("ix_identity_audit_log_action", "action_type", "created_at_utc"),
    )


class IdentityOutboxModel(Base):
    __tablename__ = "identity_outbox"

    outbox_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    partition_key: Mapped[str] = mapped_column(String(100), nullable=False, default="identity")
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    causation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    publish_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    claimed_by_worker: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim_expires_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_identity_outbox_status_attempt", "publish_status", "next_attempt_at_utc"),
        Index("ix_identity_outbox_claim_expires", "claim_expires_at_utc"),
        Index(
            "ix_identity_outbox_aggregate",
            "aggregate_type",
            "aggregate_id",
            "created_at_utc",
        ),
        Index(
            "ix_identity_outbox_partition",
            "partition_key",
            "publish_status",
            "created_at_utc",
        ),
    )


class IdentityRefreshTokenModel(Base):
    __tablename__ = "identity_refresh_tokens"

    token_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    family_id: Mapped[Optional[str]] = mapped_column(String(26), nullable=True)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_identity_refresh_tokens_user", "user_id"),
        Index("ix_identity_refresh_tokens_expires", "expires_at_utc"),
        Index("ix_identity_refresh_tokens_family", "family_id"),
    )


class IdentityWorkerHeartbeatModel(Base):
    __tablename__ = "identity_worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
