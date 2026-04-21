"""Base class for async HTTP API clients.

All external API services should inherit from BaseAPIClient to avoid
duplicating httpx.AsyncClient setup and close() boilerplate.

Services with non-standard patterns (ESPN's lazy init, Polymarket's
dual clients) can skip this base class — it's for the common case.
"""

import httpx


class BaseAPIClient:
    """Async HTTP API client with httpx.

    Subclasses call super().__init__() with their specific kwargs:

        class MyAPI(BaseAPIClient):
            BASE_URL = "https://api.example.com"
            def __init__(self, api_key: str):
                super().__init__(
                    timeout=15.0,
                    headers={"Authorization": f"Bearer {api_key}"},
                )

        service = MyAPI(api_key="...")
        resp = await service.client.get(f"{service.BASE_URL}/foo")
        await service.close()
    """

    BASE_URL: str = ""

    def __init__(self, **client_kwargs):
        kwargs = {"timeout": 30.0}
        kwargs.update(client_kwargs)
        self.client = httpx.AsyncClient(**kwargs)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
