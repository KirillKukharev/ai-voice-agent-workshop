import logging
from datetime import datetime
from typing import Any, NoReturn

import aiohttp
from aiohttp_retry import ExponentialRetry, RetryClient
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.constants import RETRY_STATUSES
from backend.core.models import APIResponse
from backend.settings import get_settings

logger = logging.getLogger(__name__)


class HttpRequestMixin:
    """Mixin for sending http requests"""

    def __init__(
        self,
        retry_attempts: int | None = None,
        start_timeout: float | None = None,
        headers: dict | None = None,
    ) -> None:
        settings = get_settings()

        self._settings = settings
        self._retry_options: ExponentialRetry = ExponentialRetry(
            attempts=retry_attempts or settings.DEFAULT_API_RETRY_COUNT,
            start_timeout=start_timeout or settings.DEFAULT_API_RETRY_START_TIMEOUT,
            retry_all_server_errors=True,
            statuses=RETRY_STATUSES,
        )
        self._headers = headers or {}

    # pylint: disable=too-many-positional-arguments
    async def _post(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        data: Any | None = None,
        json: dict[str, Any] | None = None,
        retry_options: ExponentialRetry | None = None,
    ) -> dict:
        """Post request"""
        retry_config = self._retry_options
        if retry_options is not None:
            retry_config = retry_options

        if not headers:
            headers = self._headers

        async with aiohttp.ClientSession() as session:
            retry_client = RetryClient(
                client_session=session,
                retry_options=retry_config,
                logger=logger,
                raise_for_status=True,
            )
            response = await retry_client.post(
                url,
                data=data,
                json=json,
                headers=headers,
                ssl=self._settings.VERIFY_SSL,
            )
            return await response.json(content_type=None)

    async def _get(self, url: str, headers: dict[str, Any] | None = None) -> dict:
        """Get request"""
        if not headers:
            headers = self._headers

        async with aiohttp.ClientSession() as session:
            retry_client = RetryClient(
                client_session=session,
                retry_options=self._retry_options,
                logger=logger,
                raise_for_status=True,
            )
            response = await retry_client.get(
                url,
                headers=headers,
                ssl=self._settings.VERIFY_SSL,
            )
            return await response.json(content_type=None)


class ClassNameAndAllAttrStrMixin:
    """Mixin for correct class __str__ with all attrs"""

    def __str__(self):
        return f"<{self.__class__.__name__}>: {', '.join([f'{k}={v}' for k, v in self.__dict__.items()])}"


async def make_response(api_response: BaseModel, status_code: int | None = None) -> JSONResponse:
    """Prepare API JSONResponse"""
    if isinstance(api_response, APIResponse):
        status_code = api_response.status_code

    if not status_code:
        raise ValueError("status_code not provided")

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(api_response),
    )


def generate_example_response(response_examples: list[dict] | dict, description: str = "Success") -> dict:
    """Substitution of endpoint response examples in response template description"""
    if isinstance(response_examples, dict):
        response_examples = [response_examples]

    return {
        "description": description,
        "content": {
            "application/json": {
                "examples": {response_example["summary"]: response_example for response_example in response_examples},
            },
        },
    }


async def raise_http_exception(status_code: int, message: str, **kwargs) -> NoReturn:
    """Throws HTTP exception"""
    logger.error(message)

    raise HTTPException(
        status_code=status_code,
        detail=message,
        **kwargs,
    )


def get_current_timestamp() -> int:
    return int(datetime.now().timestamp())
