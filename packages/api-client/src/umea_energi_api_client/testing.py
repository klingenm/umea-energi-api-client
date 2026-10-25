"""A stand-in for the Umeå Energi API, for testing code that uses this library.

```python
fake = FakeApi()
fake.add("GET", "/api/v1/Disturbance", httpx.Response(200, json=[]))
client = UmeaEnergiClient("https://api.test", httpx_args={"transport": fake.transport})
```
"""

import httpx


class FakeApi:
    """Answers requests by method and path. Each route replays its responses; the last repeats."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list[httpx.Response]] = {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    def add(self, method: str, path: str, *responses: httpx.Response) -> None:
        self.routes[(method, path)] = list(responses)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        responses = self.routes.get((request.method, request.url.path))
        if not responses:
            return httpx.Response(404, json={"message": f"No fake for {request.url.path}"})
        return responses.pop(0) if len(responses) > 1 else responses[0]

    def requests_to(self, path: str) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path == path]
