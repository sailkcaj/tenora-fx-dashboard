"""Minimal stand-ins for requests' Session / Response used by the source tests."""


class FakeResponse:
    def __init__(self, status_code=200, text="", content=None, headers=None):
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode()
        self.headers = headers or {}

    def iter_content(self, chunk_size=1 << 20):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]


class FakeSession:
    """Serves canned responses: a list consumed in order, or a dict keyed by URL prefix whose
    values are responses or zero-argument callables returning one."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None, stream=False):
        self.calls.append({"url": url, "params": params, "headers": headers, "stream": stream})
        if isinstance(self.responses, dict):
            for prefix, response in self.responses.items():
                if url.startswith(prefix):
                    return response() if callable(response) else response
            raise AssertionError(f"unexpected URL {url}")
        return self.responses.pop(0)
