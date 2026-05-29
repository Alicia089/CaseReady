import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str = Security(_header_scheme)) -> str:
    """
    Validates the X-API-Key header against the secret stored in the environment.
    In production this is replaced by AWS Cognito JWT validation — same interface,
    swap the implementation without touching any endpoint code.
    """
    expected = os.environ.get("CASEREADY_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: API key not set",
        )
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
