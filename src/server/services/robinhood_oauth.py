"""
Robinhood OAuth service — token validation and refresh.

Mirrors the pattern in claude_oauth.py: get_valid_token() checks expiry,
refreshes with a Redis lock when needed, and returns None when the user
hasn't connected their Robinhood account.

The refresh endpoint and client credentials will be filled in during the
OAuth onboarding implementation (Phase 3). Until then, refresh_tokens()
raises NotImplementedError — the token is returned as-is and will fail
at the MCP server if it has already expired.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from src.server.database.oauth_tokens import get_oauth_tokens, upsert_oauth_tokens

logger = logging.getLogger(__name__)

ROBINHOOD_PROVIDER = "robinhood"

# TODO(Phase 3): fill in once OAuth onboarding is implemented
ROBINHOOD_TOKEN_URL = ""
ROBINHOOD_CLIENT_ID = ""


async def refresh_tokens(refresh_token: str) -> dict:
    """Exchange a refresh token for new tokens.

    Returns:
        {access_token, refresh_token, expires_in}

    Raises:
        NotImplementedError: until Phase 3 OAuth onboarding sets the endpoint.
    """
    if not ROBINHOOD_TOKEN_URL or not ROBINHOOD_CLIENT_ID:
        raise NotImplementedError(
            "Robinhood token refresh is not yet configured. "
            "Set ROBINHOOD_TOKEN_URL and ROBINHOOD_CLIENT_ID in Phase 3."
        )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ROBINHOOD_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "client_id": ROBINHOOD_CLIENT_ID,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_in": data.get("expires_in", 3600),
        }


async def get_valid_token(user_id: str) -> dict | None:
    """Return a valid Robinhood access token, refreshing if needed.

    Uses a Redis SETNX lock to prevent concurrent refresh races.
    Returns None if the user hasn't connected their Robinhood account.
    Returns {"access_token": str} on success.
    """
    tokens = await get_oauth_tokens(user_id, ROBINHOOD_PROVIDER)
    if not tokens or not tokens.get("access_token"):
        return None

    now = datetime.now(timezone.utc)
    expires_at = tokens.get("expires_at")

    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now + timedelta(minutes=5):
            return {"access_token": tokens["access_token"]}
    else:
        # No expiry stored — assume valid (manual token or legacy row)
        return {"access_token": tokens["access_token"]}

    # Token is expiring — attempt refresh with Redis lock
    from src.utils.cache.redis_cache import get_cache_client

    cache = get_cache_client()
    lock_key = f"oauth:refresh:{user_id}:{ROBINHOOD_PROVIDER}"

    if cache.enabled and cache.client:
        acquired = await cache.client.set(lock_key, "1", nx=True, ex=35)
        if not acquired:
            await asyncio.sleep(1)
            tokens = await get_oauth_tokens(user_id, ROBINHOOD_PROVIDER)
            if tokens:
                return {"access_token": tokens["access_token"]}
            return None

    try:
        new = await refresh_tokens(tokens["refresh_token"])
        new_expires = now + timedelta(seconds=new.get("expires_in", 3600))

        await upsert_oauth_tokens(
            user_id=user_id,
            provider=ROBINHOOD_PROVIDER,
            access_token=new["access_token"],
            refresh_token=new["refresh_token"],
            account_id=tokens.get("account_id", ""),
            email=tokens.get("email"),
            plan_type=tokens.get("plan_type"),
            expires_at=new_expires,
        )

        logger.debug(f"[robinhood_oauth] Refreshed tokens for user_id={user_id}")
        return {"access_token": new["access_token"]}
    except NotImplementedError:
        logger.warning(
            f"[robinhood_oauth] Token near expiry for user_id={user_id} "
            "but refresh is not yet configured; returning existing token."
        )
        return {"access_token": tokens["access_token"]}
    except Exception as e:
        logger.error(f"[robinhood_oauth] Token refresh failed for user_id={user_id}: {e}")
        return None
    finally:
        if cache.enabled and cache.client:
            try:
                await cache.client.delete(lock_key)
            except Exception:
                pass
