from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.wikipedia import WikipediaClient


class FakeHttp:
    """Stands in for HttpClient, replaying one canned Action API response."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, params=None, accept=None):
        self.calls.append((url, params))
        return self.payload


def test_resolve_articles_separates_red_links_from_unlinked_articles():
    http = FakeHttp(
        {
            "query": {
                "redirects": [{"from": "Old Name", "to": "New Name"}],
                "pages": [
                    {"title": "Linked", "pageprops": {"wikibase_item": "Q10"}},
                    {"title": "Unlinked"},  # article exists, no item
                    {"title": "Red Link", "missing": True},
                    {"title": "New Name", "pageprops": {"wikibase_item": "Q11"}},
                ],
            }
        }
    )
    client = WikipediaClient(http, language="de")

    articles = client.resolve_articles(
        ["Linked", "Unlinked", "Red Link", "Old Name"], "de"
    )

    assert articles["Linked"] == (True, "Q10")
    assert articles["Unlinked"] == (True, None)
    assert articles["Red Link"] == (False, None)
    # Redirects are still followed to the target's item.
    assert articles["Old Name"] == (True, "Q11")
    assert http.calls[0][0] == "https://de.wikipedia.org/w/api.php"


def test_resolve_articles_defaults_to_not_found_for_a_title_the_api_omits():
    client = WikipediaClient(FakeHttp({"query": {"pages": []}}), language="en")
    assert client.resolve_articles(["Ghost"]) == {"Ghost": (False, None)}
