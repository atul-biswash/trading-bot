"""Shared credential gate for the opt-in Testnet integration tests.

The gate has to agree with how the application actually finds secrets, and
reading ``os.environ`` directly does not. Credentials normally live in ``.env``,
which ``pydantic-settings`` loads into :class:`Secrets` at call time and never
exports into the process environment. A gate built on ``os.getenv`` therefore
tells someone whose credentials are present and working that they have none --
worse than no gate at all, because the message is specific and wrong.

Asking :class:`Secrets` fixes it by construction: one place knows where secrets
come from, and the tests consult that place instead of guessing. ``Secrets`` has
a default of ``""`` for every field, so constructing it never raises when
nothing is configured -- it simply reports empty, which is the answer we want.

The pair is checked, not just the key: a key with no secret cannot authenticate,
so treating it as "credentials present" would trade a misleading skip for a
misleading failure.
"""

from __future__ import annotations

from trading_bot.config.settings import Secrets

SKIP_REASON = (
    "No Binance credentials found. Set BINANCE_TESTNET_API_KEY/SECRET (or "
    "BINANCE_API_KEY/SECRET) in .env or in the environment to run the opt-in "
    "testnet integration tests."
)


def has_credentials() -> bool:
    """Return ``True`` when a usable key/secret pair is reachable."""
    secrets = Secrets()
    testnet = bool(secrets.binance_testnet_api_key and secrets.binance_testnet_api_secret)
    primary = bool(secrets.binance_api_key and secrets.binance_api_secret)
    return testnet or primary


#: Evaluated once at import, because the skip mark is applied at collection.
HAS_CREDENTIALS = has_credentials()
