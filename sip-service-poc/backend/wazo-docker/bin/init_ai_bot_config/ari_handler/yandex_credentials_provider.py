import logging
import time
from datetime import datetime

import aiohttp
import jwt
from config.settings import app_settings

logger = logging.getLogger(__name__)


class YandexCredentialsProvider:
    def __init__(self):
        self.service_account_id = app_settings.SERVICE_ACCOUNT_ID
        self.key_id = app_settings.SA_KEY_ID
        self.private_key = app_settings.PRIVATE_KEY
        self.folder_id = app_settings.FOLDER_ID

    async def get_iam_token(self) -> tuple[str, datetime | None]:
        """Get IAM token using JWT authentication."""
        logger.info("Getting IAM token")
        jwt_token = self._generate_jwt()
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                "https://iam.api.cloud.yandex.net/iam/v1/tokens",
                json={"jwt": jwt_token},
            ) as resp,
        ):
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Yandex IAM API error {resp.status}: {error_text}")
                raise Exception(f"Failed to get IAM token: HTTP {resp.status}")

            data = await resp.json()
            token = data["iamToken"]
            expires_at_str = data.get("expiresAt", "")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                logger.info(f"IAM token expires at: {expires_at}")
                return token, expires_at
            logger.error("IAM token response missing expiresAt field")
            return token, None

    def _generate_jwt(self) -> str:
        """Generate JWT for Yandex IAM token request."""
        logger.info("Generating JWT")
        now = int(time.time())
        payload = {
            "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            "iss": self.service_account_id,
            "iat": now,
            "exp": now + 360,
            "kid": self.key_id,
        }

        try:
            token = jwt.encode(
                payload,
                self.private_key,
                algorithm="PS256",
                headers={"kid": self.key_id},
            )
            logger.info("JWT token successfully generated")
            return token
        except Exception as e:
            logger.exception("❌ Failed to generate JWT token: %s", e)
            raise
