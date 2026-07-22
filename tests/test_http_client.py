from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

import pytest

from wd_squads.http_client import HttpClient


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        import json

        return json.loads(self.text)


class FakeSession:
    """A session that records how many GETs it received and replays bodies."""

    def __init__(self, bodies):
        self.headers = {}
        self._bodies = list(bodies)
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        body = self._bodies[min(self.calls - 1, len(self._bodies) - 1)]
        return FakeResponse(body)


def _client(session):
    return HttpClient(user_agent="test", request_delay=0, session=session)


def test_invalid_json_fails_fast_without_retrying():
    # A truncated body is deterministic; retrying just returns the same thing,
    # so we should fail immediately rather than spend the retry budget.
    session = FakeSession(['{"results": {"bindings": [ "unterminated'])
    client = _client(session)

    with pytest.raises(RuntimeError, match="not valid JSON"):
        client.get_json("https://example.org/sparql", params={})

    assert session.calls == 1


def test_valid_json_is_returned():
    session = FakeSession(['{"ok": true}'])
    client = _client(session)

    assert client.get_json("https://example.org/sparql", params={}) == {"ok": True}
    assert session.calls == 1
