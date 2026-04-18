import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core import models
from backend.core.utils import make_response

logger = logging.getLogger(__name__)


async def unprocessable_entity_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """RequestValidationError handler"""
    http_exception_response = models.ErrorAPIResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, message=str(exc)
    )
    logger.error(
        "An HTTPException was thrown while processing a request along the path %s:"
        " status_code=422, message=%s, request body: %s",
        request.scope.get("path"),
        str(exc),
        await request.body(),
    )
    return await make_response(api_response=http_exception_response)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException handler"""
    http_exception_response = models.ErrorAPIResponse(status_code=exc.status_code, message=exc.detail)

    logger.error(
        "An HTTPException was thrown while processing a request along the path %s: status_code=%s, message=%s",
        request.scope.get("path"),
        exc.status_code,
        exc.detail,
    )
    # fmt: off
    logger.debug(
        "Request:\ncookies - %s\nheaders - %s\nquery - %s\npath - %s\nbody - %s\nform - %s\ntype - %s",
        request.cookies,
        request.headers,
        request.query_params,
        request.path_params,
        await request.body() if not request._stream_consumed else "",  # pylint: disable=W0212
        await request.form(),
        request.method,
    )
    # fmt: on

    return await make_response(api_response=http_exception_response)


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Unexpected error handler"""
    unexpected_exception_response = await _get_error_response_for_exception(exc=exc)

    logger.error(
        "Error in request processing logic %s: %s",
        request.scope.get("path"),
        await _get_exception_message(exc=exc),
    )

    return await make_response(api_response=unexpected_exception_response)


async def _get_exception_message(exc: Exception) -> str:
    """Get an Error, based on an Exception"""
    return f"{exc.__class__.__name__}: {str(exc)}"


async def _get_error_response_for_exception(exc: Exception) -> models.ErrorAPIResponse:
    """Get an Error, based on an specific Exception"""
    return models.ErrorAPIResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=await _get_exception_message(exc=exc),
    )
