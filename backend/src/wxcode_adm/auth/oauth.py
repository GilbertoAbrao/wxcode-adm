"""
Authlib OAuth registry for wxcode-adm.

Provides Google and GitHub OAuth 2.0 provider configurations.
Providers are only registered when their credentials are configured (non-empty)
to prevent startup crashes in dev mode when OAuth env vars are not set.

PKCE (S256) is enabled for both providers for CSRF protection without
requiring server-side state storage (authlib uses SessionMiddleware for state).

Usage:
    from wxcode_adm.auth.oauth import oauth
    client = oauth.create_client("google")  # or "github"
    await client.authorize_redirect(request, redirect_uri)
"""

from authlib.integrations.starlette_client import OAuth

from wxcode_adm.config import settings

oauth = OAuth()

# Only register providers if credentials are configured (non-empty).
# This prevents startup crash when OAuth env vars are absent (dev mode).

if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
        },
    )

if settings.GITHUB_CLIENT_ID:
    oauth.register(
        name="github",
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET.get_secret_value(),
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={
            "scope": "user:email",
            "code_challenge_method": "S256",
        },
    )
