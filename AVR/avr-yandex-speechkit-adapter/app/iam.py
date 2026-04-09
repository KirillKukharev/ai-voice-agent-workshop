"""Yandex Cloud IAM token via service account JWT (PS256), same flow as YandexCredentialsProvider."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import jwt

logger = logging.getLogger(__name__)


@dataclass
class IamState:
    token: str
    expires_at: datetime | None


def _parse_expires(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def fetch_iam_token(
    service_account_id: str,
    key_id: str,
    private_key_pem: str,
) -> tuple[str, datetime | None]:
    now = int(time.time())
    payload = {
        "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
        "iss": service_account_id,
        "iat": now,
        "exp": now + 360,
    }
    jwt_token = jwt.encode(
        payload,
        private_key_pem,
        algorithm="PS256",
        headers={"kid": key_id},
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            json={"jwt": jwt_token},
        )
    if r.status_code != 200:
        logger.error("IAM error %s: %s", r.status_code, r.text)
        r.raise_for_status()
    data = r.json()
    token = data["iamToken"]
    exp = _parse_expires(data.get("expiresAt"))
    return token, exp


class IamTokenProvider:
    """Caches IAM token and refreshes ~60s before expiry."""

    def __init__(
        self,
        service_account_id: str,
        key_id: str,
        private_key_pem: str,
    ):
        self._sa = service_account_id
        self._kid = key_id
        self._key = private_key_pem
        self._state: IamState | None = None
        self._async_lock = asyncio.Lock()

    async def get_token(self) -> str:
        now = datetime.now(timezone.utc)
        async with self._async_lock:
            if self._state and self._state.expires_at:
                if self._state.expires_at - timedelta(seconds=60) > now:
                    return self._state.token
            token, exp = await fetch_iam_token(self._sa, self._kid, self._key)
            self._state = IamState(token=token, expires_at=exp)
            logger.info("IAM token refreshed, expires_at=%s", exp)
            return token
