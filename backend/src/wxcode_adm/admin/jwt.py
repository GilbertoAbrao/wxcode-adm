"""
Admin JWT utility module for wxcode-adm.

Provides admin-audience token creation and decoding. Admin tokens carry
aud="wxcode-adm-admin" which creates bidirectional isolation:
- decode_admin_access_token rejects tokens without the correct aud claim.
- decode_access_token (regular, no audience param) rejects admin tokens
  because PyJWT 2.11.0 treats an aud claim in the payload as requiring
  audience verification — passing no audience raises InvalidTokenError.

Token structure:
    sub   — user ID (UUID string)
    aud   — "wxcode-adm-admin" (admin audience)
    iat   — issued-at timestamp
    exp   — expiry timestamp
    jti   — unique token identifier (UUID, for replay detection)
    kid   — key ID (in JWT header, matches JWKS kid)
"""

import jwt

from wxcode_adm.auth.exceptions import InvalidTokenError, TokenExpiredError
from wxcode_adm.auth.jwt import create_access_token
from wxcode_adm.config import settings


def create_admin_access_token(user_id: str) -> str:
    """
    Create an RS256-signed JWT access token with admin audience claim.

    Thin wrapper around create_access_token that adds aud="wxcode-adm-admin"
    so the token is accepted by decode_admin_access_token and rejected by
    the regular decode_access_token.

    Args:
        user_id: The super-admin user's UUID string (stored as 'sub' claim).

    Returns:
        A compact RS256 JWT string with aud="wxcode-adm-admin".
    """
    return create_access_token(user_id, extra_claims={"aud": "wxcode-adm-admin"})


def decode_admin_access_token(token: str) -> dict:
    """
    Decode and verify an RS256-signed admin JWT access token.

    Enforces aud="wxcode-adm-admin" — regular user tokens (without aud)
    are rejected by PyJWT 2.11.0 because the expected audience is specified
    but missing from the token.

    Args:
        token: The compact JWT string to decode.

    Returns:
        The decoded payload dict on success.

    Raises:
        TokenExpiredError: If the token's exp claim is in the past.
        InvalidTokenError: If the token signature is invalid, malformed,
                           missing the correct aud claim, or otherwise rejected.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY.get_secret_value(),
            algorithms=["RS256"],
            audience="wxcode-adm-admin",
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidTokenError()
    return payload
