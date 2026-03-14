"""
JWT utility module for wxcode-adm.

Provides RS256 token creation and decoding using PyJWT.
Tokens are signed with the RSA private key stored in settings and can be
verified by external services using the public key served at /.well-known/jwks.json.

Token structure:
    sub       — user ID (UUID string)
    aud       — "wxcode-adm" for regular tokens
    tenant_id — current tenant UUID when available
    role      — current tenant role when available
    iat       — issued-at timestamp
    exp       — expiry timestamp
    jti       — unique token identifier (UUID, for replay detection)
    kid       — key ID (in JWT header, matches JWKS kid)
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from wxcode_adm.auth.exceptions import InvalidTokenError, TokenExpiredError
from wxcode_adm.config import settings


def create_access_token(user_id: str, extra_claims: dict | None = None) -> str:
    """
    Create an RS256-signed JWT access token.

    Args:
        user_id: The user's UUID string (stored as 'sub' claim).
        extra_claims: Optional additional claims merged into the payload.

    Returns:
        A compact RS256 JWT string.
    """
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": user_id,
        "aud": "wxcode-adm",
        "iat": now,
        "exp": now + timedelta(hours=settings.ACCESS_TOKEN_TTL_HOURS),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)

    # kid is placed in the JOSE header, NOT in the payload
    token: str = jwt.encode(
        payload,
        settings.JWT_PRIVATE_KEY.get_secret_value(),
        algorithm="RS256",
        headers={"kid": settings.JWT_KID},
    )
    return token


def decode_access_token(token: str) -> dict:
    """
    Decode and verify an RS256-signed JWT access token.

    Args:
        token: The compact JWT string to decode.

    Returns:
        The decoded payload dict on success.

    Raises:
        TokenExpiredError: If the token's exp claim is in the past.
        InvalidTokenError: If the token signature is invalid, malformed, or otherwise rejected.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY.get_secret_value(),
            algorithms=["RS256"],
            audience="wxcode-adm",
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidTokenError()
    return payload
