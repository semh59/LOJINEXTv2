import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.models import IdentityAuditLogModel, IdentityUserModel
from identity_service.token_service import (
    issue_token_pair,
    seed_bootstrap_state,
    serialize_user,
)


@pytest.mark.asyncio
async def test_audit_masking_integrity(session: AsyncSession):
    """
    Scan audit snapshots for unmasked emails to ensure forensic airtightness.
    """
    await seed_bootstrap_state(session)
    user = (await session.execute(select(IdentityUserModel).limit(1))).scalar_one()

    # Create a fresh audit log via serialization
    from identity_service.token_service import _write_audit

    await _write_audit(
        session,
        "USER",
        user.user_id,
        "UPDATE",
        "ADMIN",
        "SUPER_ADMIN",
        new_snapshot=serialize_user(user, mask_pii=True),
    )
    await session.commit()

    # Scan the DB for any unmasked emails in snapshots
    result = await session.execute(select(IdentityAuditLogModel))
    logs = result.scalars().all()

    for log in logs:
        # Check new snapshot
        if log.new_snapshot_json:
            # If the raw email (e.g. 'admin@lojinest.com') is in the JSON, fail.
            # We expect 'a***n@lojinest.com'
            assert user.email not in log.new_snapshot_json, (
                f"PII Leak detected in audit snapshot! ID: {log.audit_id}"
            )


@pytest.mark.asyncio
async def test_security_jwt_integrity(session: AsyncSession):
    """
    Verify that RS256 signature mutation is detected and rejected.
    """
    await seed_bootstrap_state(session)
    user = (await session.execute(select(IdentityUserModel).limit(1))).scalar_one()

    token_pair = await issue_token_pair(session, user)
    token = token_pair["access_token"]

    # Mutate the payload portion of the JWT
    header, payload, signature = token.split(".")
    import base64
    import json

    # Decode payload
    pad = "=" * (4 - len(payload) % 4)
    payload_dict = json.loads(base64.urlsafe_b64decode(payload + pad))

    # Elevate role
    payload_dict["role"] = "ULTIMATE_HACKER"

    # Re-encode mutated payload
    mutated_payload = (
        base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).decode().rstrip("=")
    )

    mutated_token = f"{header}.{mutated_payload}.{signature}"

    # Attempt to decode via service
    from identity_service.token_service import decode_access_token

    with pytest.raises(Exception):
        await decode_access_token(session, mutated_token)
