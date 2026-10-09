from collections.abc import AsyncIterator

import httpx
import pytest

from planner.bootstrap import Container
from planner.entrypoints.api.app import create_app
from planner.settings import Settings


@pytest.fixture
async def client(settings: Settings, container: Container) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, container)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined] — tests reach the bot dispatcher through it
            yield c
