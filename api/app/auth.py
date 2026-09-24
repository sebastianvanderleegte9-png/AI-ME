from fastapi import Header, HTTPException, status

from .settings import settings


def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Component 0 auth: a shared key. Component 1 replaces this with founder logins
    (Clerk) and per-company scoping. Kept as a dependency so routers don't change."""
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
