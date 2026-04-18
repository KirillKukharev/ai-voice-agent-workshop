import logging

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials

from backend.api.v1.auth import constants
from backend.api.v1.auth.security import oauth2_scheme
from backend.core.utils import raise_http_exception
from backend.settings import get_settings

logger = logging.getLogger(__name__)


class AppTokenValidatorService:
    """Token validator Service"""

    def __init__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    ) -> None:
        self._settings = get_settings()
        self._credentials = credentials

    async def validate(self) -> None:
        """Process of token validation"""
        if not self._credentials:
            logger.info("Credentials are not provided")

            await raise_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message=constants.APIResponseMessageTemplate.UNAUTHORIZED,
            )

        if not self._is_valid_token(token=self._credentials.credentials):
            logger.info("Token validation failed")

            await raise_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                message=constants.APIResponseMessageTemplate.FORBIDDEN,
            )

    def _is_valid_token(self, token: str) -> bool:
        """Validate token"""
        return token == self._settings.APP_TOKEN


class AppTokenValidator:
    """Token validator class"""

    async def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    ):
        _validator_service = AppTokenValidatorService(credentials=credentials)
        await _validator_service.validate()
