"""Deep auth-branch coverage for trip-service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from platform_auth import ServiceTokenAcquisitionError, TokenInvalidError, TokenMissingError

import trip_service.auth as auth_module
from trip_service.auth import (
    admin_or_internal_auth_dependency,
    auth_outbound_status,
    auth_verify_status,
    issue_internal_service_token,
    require_service_token,
    require_user_token,
)
from trip_service.enums import ActorType

pytestmark = pytest.mark.unit


def _claims(*, sub: str = "user-001", role: str = "MANAGER", service: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(sub=sub, role=role, service=service)


@pytest.mark.parametrize(
    ("settings_obj", "expected"),
    [
        (SimpleNamespace(uses_hmac=True, shared_secret=None, uses_rsa=False), "fail"),
        (SimpleNamespace(uses_hmac=False, shared_secret=None, uses_rsa=True, issuer="", audience="aud"), "fail"),
        (SimpleNamespace(uses_hmac=False, shared_secret=None, uses_rsa=True, issuer="iss", audience=""), "fail"),
        (
            SimpleNamespace(
                uses_hmac=False,
                shared_secret=None,
                uses_rsa=True,
                issuer="iss",
                audience="aud",
                public_key="",
                jwks_url="",
            ),
            "fail",
        ),
    ],
)
def test_auth_verify_status_rejects_invalid_local_settings(
    monkeypatch: pytest.MonkeyPatch,
    settings_obj: SimpleNamespace,
    expected: str,
) -> None:
    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    assert auth_verify_status() == expected


def test_auth_verify_status_returns_fail_when_provider_build_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_obj = SimpleNamespace(
        uses_hmac=False,
        shared_secret=None,
        uses_rsa=True,
        issuer="iss",
        audience="aud",
        public_key="pem",
        jwks_url="",
    )
    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    monkeypatch.setattr(
        auth_module,
        "build_verification_provider",
        lambda _: (_ for _ in ()).throw(RuntimeError("bad")),
    )

    assert auth_verify_status() == "fail"


def test_auth_verify_status_returns_ok_for_valid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_obj = SimpleNamespace(
        uses_hmac=False,
        shared_secret=None,
        uses_rsa=True,
        issuer="iss",
        audience="aud",
        public_key="pem",
        jwks_url="",
    )
    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    monkeypatch.setattr(auth_module, "build_verification_provider", lambda _: object())

    assert auth_verify_status() == "ok"


@pytest.mark.parametrize(
    "settings_obj",
    [
        SimpleNamespace(uses_hmac=True, private_key=None, audience="aud"),
        SimpleNamespace(uses_hmac=False, private_key="pem", audience="aud"),
    ],
)
def test_auth_outbound_status_returns_ok_for_local_signing(
    monkeypatch: pytest.MonkeyPatch,
    settings_obj: SimpleNamespace,
) -> None:
    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    assert auth_outbound_status() == "ok"


def test_auth_outbound_status_uses_cache_readiness_for_remote_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_obj = SimpleNamespace(uses_hmac=False, private_key="", audience="remote-aud")
    captured: dict[str, object] = {}

    def fake_readiness_state(**kwargs):
        captured["kwargs"] = kwargs
        return "cold"

    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    monkeypatch.setattr(auth_module._SERVICE_TOKEN_CACHE, "readiness_state", fake_readiness_state)

    result = auth_outbound_status(audience="fleet-service")

    assert result == "cold"
    assert captured["kwargs"] == {
        "service_name": auth_module.settings.service_name,
        "audience": "remote-aud",
        "token_url": auth_module.settings.auth_service_token_url,
        "client_id": auth_module.settings.auth_service_client_id,
        "client_secret": auth_module.settings.auth_service_client_secret,
    }


@pytest.mark.asyncio
async def test_issue_internal_service_token_issues_locally_for_hmac(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_obj = SimpleNamespace(uses_hmac=True, private_key=None, audience="fleet-service")
    captured: dict[str, object] = {}

    class FakeFactory:
        def __init__(self, *, service_name: str, settings: object) -> None:
            captured["service_name"] = service_name
            captured["settings"] = settings

        def issue(self) -> str:
            return "local-token"

    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    monkeypatch.setattr(auth_module, "ServiceTokenFactory", FakeFactory)

    assert await issue_internal_service_token(audience="fleet-service") == "local-token"
    assert captured["service_name"] == auth_module.settings.service_name
    assert captured["settings"] is settings_obj


@pytest.mark.asyncio
async def test_issue_internal_service_token_uses_remote_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_obj = SimpleNamespace(uses_hmac=False, private_key="", audience="fleet-service")
    captured: dict[str, object] = {}

    async def fake_get_token(**kwargs) -> str:
        captured.update(kwargs)
        return "remote-token"

    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    monkeypatch.setattr(auth_module._SERVICE_TOKEN_CACHE, "get_token", fake_get_token)

    assert await issue_internal_service_token(audience="fleet-service") == "remote-token"
    assert captured == {
        "service_name": auth_module.settings.service_name,
        "audience": "fleet-service",
        "token_url": auth_module.settings.auth_service_token_url,
        "client_id": auth_module.settings.auth_service_client_id,
        "client_secret": auth_module.settings.auth_service_client_secret,
    }


@pytest.mark.asyncio
async def test_issue_internal_service_token_wraps_acquisition_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_obj = SimpleNamespace(uses_hmac=False, private_key="", audience="fleet-service")

    async def fake_get_token(**kwargs) -> str:
        del kwargs
        raise ServiceTokenAcquisitionError("token fetch failed")

    monkeypatch.setattr(auth_module, "_platform_auth_settings", lambda audience=None: settings_obj)
    monkeypatch.setattr(auth_module._SERVICE_TOKEN_CACHE, "get_token", fake_get_token)

    with pytest.raises(RuntimeError, match="token fetch failed"):
        await issue_internal_service_token(audience="fleet-service")


def test_decode_claims_maps_missing_token_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "decode_bearer_token",
        lambda authorization, settings: (_ for _ in ()).throw(TokenMissingError("missing")),
    )

    with pytest.raises(Exception) as exc_info:
        auth_module._decode_claims(None)

    assert getattr(exc_info.value, "code", None) == "TRIP_AUTH_REQUIRED"


def test_decode_claims_maps_invalid_token_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "decode_bearer_token",
        lambda authorization, settings: (_ for _ in ()).throw(TokenInvalidError("bad token")),
    )

    with pytest.raises(Exception) as exc_info:
        auth_module._decode_claims("Bearer bad")

    assert getattr(exc_info.value, "code", None) == "TRIP_AUTH_INVALID"


def test_require_user_token_maps_legacy_admin_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="ADMIN"))

    context = require_user_token("Bearer token")

    assert context.actor_id == "user-001"
    assert context.actor_type == ActorType.MANAGER.value
    assert context.role == ActorType.MANAGER.value


def test_require_user_token_rejects_unknown_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="SERVICE"))

    with pytest.raises(Exception) as exc_info:
        require_user_token("Bearer token")

    assert getattr(exc_info.value, "code", None) == "TRIP_FORBIDDEN"


def test_require_user_token_rejects_blank_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(sub="   ", role="MANAGER"))

    with pytest.raises(Exception) as exc_info:
        require_user_token("Bearer token")

    assert getattr(exc_info.value, "code", None) == "TRIP_AUTH_INVALID"


def test_require_service_token_accepts_allowed_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="SERVICE", service="fleet-service"))

    context = require_service_token("Bearer token", {"fleet-service"})

    assert context.role == ActorType.SERVICE.value
    assert context.service_name == "fleet-service"


def test_require_service_token_rejects_unknown_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="SERVICE", service="rogue"))

    with pytest.raises(Exception) as exc_info:
        require_service_token("Bearer token", {"fleet-service"})

    assert getattr(exc_info.value, "code", None) == "TRIP_FORBIDDEN"


def test_require_service_token_rejects_missing_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "_decode_claims",
        lambda _: _claims(sub=" ", role="SERVICE", service="fleet-service"),
    )

    with pytest.raises(Exception) as exc_info:
        require_service_token("Bearer token", {"fleet-service"})

    assert getattr(exc_info.value, "code", None) == "TRIP_FORBIDDEN"


def test_admin_or_internal_auth_dependency_accepts_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="SUPER_ADMIN"))

    context = admin_or_internal_auth_dependency("Bearer token")

    assert context.role == ActorType.SUPER_ADMIN.value
    assert context.actor_type == ActorType.SUPER_ADMIN.value


def test_admin_or_internal_auth_dependency_accepts_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="SERVICE", service="fleet-service"))

    context = admin_or_internal_auth_dependency("Bearer token")

    assert context.role == ActorType.SERVICE.value
    assert context.service_name == "fleet-service"


def test_admin_or_internal_auth_dependency_rejects_operatorless_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_decode_claims", lambda _: _claims(role="VIEWER"))

    with pytest.raises(Exception) as exc_info:
        admin_or_internal_auth_dependency("Bearer token")

    assert getattr(exc_info.value, "code", None) == "TRIP_FORBIDDEN"
