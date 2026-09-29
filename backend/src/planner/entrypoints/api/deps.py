from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from planner.application.principal import Principal
from planner.bootstrap import Container
from planner.modules.analytics.catalog import DisplayMode, Platform
from planner.modules.identity.service import AuthError

CLIENT_PLATFORMS = {Platform.PWA, Platform.TELEGRAM_MINI_APP}


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_principal(request: Request, c: ContainerDep) -> Principal | None:
    """Bearer access token → Principal. Missing token = anonymous; a bad token is a 401, not anonymous."""
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "invalid authorization header", headers={"WWW-Authenticate": "Bearer"})
    try:
        principal = c.identity.decode_access(token)
    except AuthError:
        raise HTTPException(401, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"}) from None
    request.state.principal = principal  # read by the activity middleware (DAU)
    return principal


async def require_principal(principal: Annotated[Principal | None, Depends(get_principal)]) -> Principal:
    if principal is None:
        raise HTTPException(401, "authentication required", headers={"WWW-Authenticate": "Bearer"})
    return principal


def parse_platform(value: str | None) -> Platform | None:
    try:
        platform = Platform(value or Platform.PWA)
    except ValueError:
        return None
    return platform if platform in CLIENT_PLATFORMS else None


def client_platform(x_client_platform: Annotated[str | None, Header()] = None) -> Platform:
    platform = parse_platform(x_client_platform)
    if platform is None:
        raise HTTPException(400, "unsupported X-Client-Platform")
    return platform


def display_mode(x_display_mode: Annotated[str | None, Header()] = None) -> DisplayMode | None:
    if x_display_mode is None:
        return None
    try:
        return DisplayMode(x_display_mode)
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


PrincipalDep = Annotated[Principal | None, Depends(get_principal)]
AuthDep = Annotated[Principal, Depends(require_principal)]
PlatformDep = Annotated[Platform, Depends(client_platform)]
DisplayModeDep = Annotated[DisplayMode | None, Depends(display_mode)]
ClientIpDep = Annotated[str, Depends(client_ip)]
