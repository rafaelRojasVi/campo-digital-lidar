"""Safety guard for production startup with an incomplete identity provider.

Mirrors app.db_safety's shape: a small, explicit precondition checked once
at startup rather than discovered later as a confusing runtime 503 on the
first real sign-in attempt.
"""

from __future__ import annotations

from app.config import Settings


class ProductionIdentityNotConfiguredError(RuntimeError):
    """Production is missing configuration required to authenticate anyone."""


def _provider_credentials(settings: Settings) -> dict[str, tuple[tuple[str, object], ...]]:
    """The credential pair each supported identity provider needs, by name."""

    return {
        "Microsoft Entra": (
            ("ENTRA_CLIENT_ID", settings.entra_client_id),
            ("ENTRA_CLIENT_SECRET", settings.entra_client_secret),
        ),
        "Google Workspace": (
            ("GOOGLE_CLIENT_ID", settings.google_client_id),
            ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
        ),
    }


def require_production_identity_configuration(settings: Settings) -> None:
    """Require a token-encryption key and one complete identity provider.

    The platform now runs two providers side by side -- Microsoft Entra for
    LiDAR and Forestal, Google Workspace for Transelec (ADR-010) -- and a
    deployment is expected to configure the ones it actually offers. So the
    requirement is not "Entra is configured"; it is:

    - ``PLATFORM_TOKEN_ENCRYPTION_KEY``, which both providers' flow cookies
      depend on; and
    - at least one provider configured COMPLETELY. A production deployment
      with no complete provider cannot authenticate anyone at all.

    A half-configured provider fails closed even when the other one is
    complete: an operator who set ``GOOGLE_CLIENT_ID`` and forgot the secret
    has shipped a sign-in button that can only ever answer 503, and should
    find that out at startup rather than from the client.

    Every other APP_ENV may run with all of this unset: development and test
    do not reach the sign-in routers in practice, and staging is documented
    (ADR-006) as having no working sign-in until the same configuration is
    supplied there too.
    """

    if settings.app_env != "production":
        return

    providers = _provider_credentials(settings)
    missing: list[str] = []

    if not settings.platform_token_encryption_key:
        missing.append("PLATFORM_TOKEN_ENCRYPTION_KEY")

    complete: list[str] = []
    for provider, credentials in providers.items():
        present = [name for name, value in credentials if value]
        if len(present) == len(credentials):
            complete.append(provider)
        elif present:
            # Partially configured: name only what is actually absent.
            missing.extend(name for name, value in credentials if not value)

    if not complete:
        # Nothing was configured at all (a partially configured provider has
        # already contributed its own missing names above).
        missing.extend(
            name
            for credentials in providers.values()
            for name, value in credentials
            if not value and name not in missing
        )

    if missing:
        raise ProductionIdentityNotConfiguredError(
            "APP_ENV=production requires identity configuration that is missing: "
            + ", ".join(missing)
        )
