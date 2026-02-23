"""
Auth router for wxcode-adm.

Currently provides:
- GET /.well-known/jwks.json — public RSA key in JWKS format for JWT verification

The JWKS endpoint is mounted WITHOUT an API prefix because /.well-known/jwks.json
is a standard path (RFC 5785) that must be accessible at the root of the domain.
External services (e.g., wxcode engine) fetch this URL to verify JWTs issued by
wxcode-adm.

Future auth endpoints (login, signup, refresh, logout) will be added in Plan 02
under the /api/v1/auth prefix.
"""

from fastapi import APIRouter

from wxcode_adm.auth.jwks import build_jwks_response
from wxcode_adm.config import settings

router = APIRouter(tags=["auth"])


@router.get("/.well-known/jwks.json")
async def jwks_endpoint() -> dict:
    """
    Return the RSA public key in JWKS (JSON Web Key Set) format.

    This endpoint is public — no authentication required. It allows any
    service to retrieve the public key needed to verify JWTs issued by
    wxcode-adm.
    """
    return build_jwks_response(
        settings.JWT_PUBLIC_KEY.get_secret_value(),
        kid=settings.JWT_KID,
    )
