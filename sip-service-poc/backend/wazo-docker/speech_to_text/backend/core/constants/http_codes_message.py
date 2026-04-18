from backend.core.constants.base import AppStringEnum


class HTTPCodesMessage(AppStringEnum):
    """HTTP codes messages"""

    HTTP_200_OK = "Successful response"
    HTTP_307_TEMPORARY_REDIRECT = "Temporary Redirect"
    HTTP_400_BAD_REQUEST = "Bad request"
    HTTP_401_UNAUTHORIZED = "Unauthorized"
    HTTP_403_FORBIDDEN = "Forbidden"
    HTTP_404_NOT_FOUND = "Not found"
    HTTP_429_TOO_MANY_REQUESTS = "Too many requests"
    HTTP_500_INTERNAL_SERVER_ERROR = "Internal server error"
    HTTP_503_SERVICE_UNAVAILABLE = "Service Unavailable"
