"""
Stripe API client singleton for wxcode-adm.

Uses the modern StripeClient pattern (not the legacy stripe.api_key global).
All async calls use the _async suffix on methods, e.g.:
    await stripe_client.products.create_async(params={...})
    await stripe_client.prices.create_async(params={...})
    await stripe_client.billing.meters.create_async(params={...})

This module is imported by billing/service.py for all Stripe API interactions.
"""

from stripe import StripeClient

from wxcode_adm.config import settings

stripe_client: StripeClient = StripeClient(
    settings.STRIPE_SECRET_KEY.get_secret_value(),
)
