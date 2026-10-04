"""Token verification.

Two modes:

* ``firebase`` — verify a Firebase ID token with the Admin SDK (production).
* ``dev`` — self-issued HS256 JWTs so the app runs with no cloud account.

Both satisfy ``TokenVerifier``, so nothing downstream knows the difference.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol

import jwt

from app.core.config import Settings
from app.core.errors import ButtlrError, UnauthenticatedError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class VerifiedIdentity:
    user_id: str
    email: str
    display_name: str
    photo_url: str | None = None
    provider: str = "dev"


class TokenVerifier(Protocol):
    mode: str

    async def verify(self, token: str) -> VerifiedIdentity: ...


class DevTokenVerifier:
    """Issues and verifies HS256 tokens signed with a local secret."""

    mode = "dev"

    def __init__(self, secret: str, ttl_hours: int = 168) -> None:
        self._secret = secret
        self._ttl_hours = ttl_hours

    def issue(self, user_id: str, email: str, display_name: str) -> tuple[str, int]:
        ttl_seconds = self._ttl_hours * 3600
        now = int(time.time())
        payload = {
            "sub": user_id,
            "email": email,
            "name": display_name,
            "iat": now,
            "exp": now + ttl_seconds,
            "iss": "buttlr-dev",
        }
        return jwt.encode(payload, self._secret, algorithm="HS256"), ttl_seconds

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            payload: dict[str, Any] = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            raise UnauthenticatedError("Your session expired. Sign in again.") from exc
        except jwt.PyJWTError as exc:
            raise UnauthenticatedError("Invalid session token.") from exc

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthenticatedError("Invalid session token.")
        email = payload.get("email") or f"{user_id}@buttlr.local"
        return VerifiedIdentity(
            user_id=user_id,
            email=email,
            display_name=payload.get("name") or email.split("@")[0],
            photo_url=payload.get("picture"),
            provider="dev",
        )


class FirebaseTokenVerifier:
    mode = "firebase"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._initialised = False

    def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        import firebase_admin
        from firebase_admin import credentials

        project_id = self._settings.firebase_project_id
        if not project_id:
            raise ButtlrError(
                "AUTH_MODE=firebase needs FIREBASE_PROJECT_ID so ID tokens can be checked.",
                code="firebase_misconfigured",
                status_code=500,
            )

        if not firebase_admin._apps:
            options: dict[str, str] = {"projectId": project_id}
            if self._settings.firebase_credentials_json:
                import json

                cred: credentials.Base | None = credentials.Certificate(
                    json.loads(self._settings.firebase_credentials_json)
                )
            elif self._settings.firebase_credentials_path:
                cred = credentials.Certificate(self._settings.firebase_credentials_path)
            else:
                # ID tokens are verified against Google's public certificates when
                # ``check_revoked=False``, so sign-in works with the project id alone. Anything
                # that calls the Admin API — revocation checks, Firestore, Storage — needs a
                # service account, and says so when it is missing.
                cred = None
                logger.warning(
                    "no Firebase service account configured: ID tokens will be verified, but "
                    "Firestore and Admin API calls need FIREBASE_CREDENTIALS_JSON or "
                    "FIREBASE_CREDENTIALS_PATH"
                )
            if cred is not None:
                firebase_admin.initialize_app(cred, options)
            else:
                firebase_admin.initialize_app(options=options)
        self._initialised = True

    async def verify(self, token: str) -> VerifiedIdentity:
        from firebase_admin import auth as fb_auth

        self._ensure_initialised()
        # Revocation ("this account was deleted or signed out everywhere") is only visible to
        # the Admin API, which needs a service account. Without one we verify the signature,
        # issuer, audience and expiry against Google's public certificates, and say so.
        check_revoked = bool(
            self._settings.firebase_credentials_json or self._settings.firebase_credentials_path
        )
        try:
            decoded = await asyncio.to_thread(
                fb_auth.verify_id_token, token, check_revoked=check_revoked
            )
        except Exception as exc:
            logger.warning("firebase token rejected: %s", exc)
            raise UnauthenticatedError("Your session expired. Sign in again.") from exc
        return VerifiedIdentity(
            user_id=decoded["uid"],
            email=decoded.get("email") or f"{decoded['uid']}@buttlr.local",
            display_name=decoded.get("name") or (decoded.get("email") or "Member").split("@")[0],
            photo_url=decoded.get("picture"),
            provider="firebase",
        )


def build_verifier(settings: Settings) -> TokenVerifier:
    if settings.auth_mode == "firebase":
        return FirebaseTokenVerifier(settings)
    return DevTokenVerifier(settings.dev_auth_secret, settings.dev_auth_ttl_hours)
