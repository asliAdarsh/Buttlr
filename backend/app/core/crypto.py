"""Secret encryption at rest.

Integration credentials (GitHub tokens, Jira API tokens, OAuth refresh tokens) are
encrypted before they are written to the store and decrypted only when a tool actually
needs them. The UI only ever sees ``mask_secret`` output.

The key comes from ``ENCRYPTION_KEY``. When that is unset we derive one from the dev auth
secret so local development still encrypts at rest rather than writing plaintext.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import ButtlrError
from app.core.logging import get_logger

logger = get_logger(__name__)

ENCRYPTION_PREFIX = "enc:v1:"


def _derive_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    configured = settings.encryption_key
    if configured:
        try:
            return Fernet(configured.encode("utf-8"))
        except (ValueError, TypeError):
            logger.warning("ENCRYPTION_KEY is not a valid Fernet key; deriving a key instead.")
    return Fernet(_derive_key(settings.dev_auth_secret))


def encrypt_secret(value: str) -> str:
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTION_PREFIX}{token}"


def decrypt_secret(value: str) -> str:
    if not value:
        return value
    if not value.startswith(ENCRYPTION_PREFIX):
        # Legacy/plaintext value: return as-is so a partially migrated store still works.
        return value
    token = value[len(ENCRYPTION_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ButtlrError(
            "A stored credential could not be decrypted. Reconnect the integration.",
            code="credential_unreadable",
            status_code=409,
        ) from exc


def mask_secret(value: str | None, *, visible: int = 4) -> str:
    if not value:
        return ""
    tail = value[-visible:] if len(value) > visible else value
    return f"{'•' * max(4, min(12, len(value) - visible))}{tail}"


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(ENCRYPTION_PREFIX)


def seal_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    """Encrypt every string leaf of a credentials document."""
    return {key: _seal_value(value) for key, value in payload.items()}


def unseal_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _unseal_value(value) for key, value in payload.items()}


def _seal_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if is_encrypted(value) else encrypt_secret(value)
    if isinstance(value, dict):
        return {k: _seal_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_seal_value(v) for v in value]
    return value


def _unseal_value(value: Any) -> Any:
    if isinstance(value, str):
        return decrypt_secret(value)
    if isinstance(value, dict):
        return {k: _unseal_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unseal_value(v) for v in value]
    return value
