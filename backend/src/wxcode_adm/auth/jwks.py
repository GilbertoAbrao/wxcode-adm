"""
JWKS (JSON Web Key Set) response builder for wxcode-adm.

Converts an RSA public key in PEM format to a JWK (JSON Web Key) representation
suitable for the /.well-known/jwks.json endpoint. External services (e.g., wxcode)
use this endpoint to retrieve the public key for JWT verification.

Reference: RFC 7517 (JSON Web Key), RFC 7518 (JSON Web Algorithms)
"""

import json

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt.algorithms import RSAAlgorithm


def build_jwks_response(public_key_pem: str, kid: str = "v1") -> dict:
    """
    Build a JWKS response dict from an RSA public key in PEM format.

    Args:
        public_key_pem: RSA public key in PEM format (SubjectPublicKeyInfo).
        kid: Key ID to embed in the JWK. Must match the kid used in JWT headers.

    Returns:
        A dict representing the JWKS document:
        {
            "keys": [
                {
                    "kty": "RSA",
                    "n": "<base64url-encoded modulus>",
                    "e": "<base64url-encoded exponent>",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": "<kid>"
                }
            ]
        }
    """
    # Load PEM — no backend= argument, load_pem_public_key uses the default backend automatically
    pub_key = load_pem_public_key(public_key_pem.encode())

    # Convert to JWK JSON string using PyJWT's RSAAlgorithm helper
    jwk_str = RSAAlgorithm.to_jwk(pub_key)
    jwk_dict = json.loads(jwk_str)

    # Add standard JWKS fields: key use, algorithm, and key ID
    jwk_dict.update({"use": "sig", "alg": "RS256", "kid": kid})

    return {"keys": [jwk_dict]}
