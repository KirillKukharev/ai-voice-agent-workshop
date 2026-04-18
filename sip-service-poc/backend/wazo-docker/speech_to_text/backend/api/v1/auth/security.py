import logging

# noinspection PyPackageRequirements
from fastapi.security import HTTPBearer

logger = logging.getLogger(__name__)


oauth2_scheme = HTTPBearer(auto_error=False)
