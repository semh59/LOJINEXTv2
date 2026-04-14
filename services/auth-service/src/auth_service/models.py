from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class AuthCredentials(Base):
    __tablename__ = "auth_credentials"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)

    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class AuthOutboxModel(Base):
    __tablename__ = "auth_outbox"

    outbox_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False, default="USER")
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(nullable=False, default=1)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(String(100), nullable=False, default="auth")
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    causation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    publish_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    claimed_by_worker: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_expires_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_auth_outbox_status_attempt_created", "publish_status", "next_attempt_at_utc", "created_at_utc"),
        Index("ix_auth_outbox_aggregate", "aggregate_type", "aggregate_id", "created_at_utc"),
        Index("ix_auth_outbox_event_name", "event_name", "created_at_utc"),
        Index("ix_auth_outbox_claim_expires", "claim_expires_at_utc"),
        Index("ix_auth_outbox_partition", "partition_key", "publish_status", "created_at_utc"),
    )

class AuthWorkerHeartbeatModel(Base):
    __tablename__ = "auth_worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class AuthRefreshTokenModel(Base):
    __tablename__ = "auth_refresh_tokens"

    token_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class AuthSigningKeyModel(Base):
    __tablename__ = "auth_signing_keys"

    kid: Mapped[str] = mapped_column(String(26), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text(), nullable=False)
    private_key_ciphertext_b64: Mapped[str] = mapped_column(Text(), nullable=False)
    private_key_kek_version: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class AuthServiceClientModel(Base):
    __tablename__ = "auth_service_clients"

    client_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    client_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class AuthAuditLogModel(Base):
    __tablename__ = "auth_audit_log"

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
        Index("ix_auth_audit_log_target", "target_type", "target_id", "created_at_utc"),
        Index("ix_auth_audit_log_actor", "actor_id", "created_at_utc"),
        Index("ix_auth_audit_log_action", "action_type", "created_at_utc"),
    )
