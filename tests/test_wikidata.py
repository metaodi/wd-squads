from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.config import Config, League
from wd_squads.wikidata import WikidataClient, _title_from_article_url


def test_title_from_article_url_respects_language():
    de = "https://de.wikipedia.org/wiki/FC_Basel"
    assert _title_from_article_url(de, "de") == "FC Basel"
    # A URL from a different edition than expected is ignored.
    assert _title_from_article_url(de, "en") is None


def test_league_query_excludes_ended_memberships():
    query = WikidataClient._league_query("Q331268", "de")

    # Walk the statement node so qualifiers are visible (not the truthy wdt:).
    assert "p:P118 ?membership" in query
    assert "ps:P118 wd:Q331268" in query
    assert "wdt:P118" not in query

    # A membership whose end time (P582) is in the past is filtered out.
    assert "pq:P582 ?end" in query
    assert "NOW()" in query
    assert "FILTER NOT EXISTS" in query

    # Deprecated-rank statements stay excluded (as wdt: did).
    assert "wikibase:DeprecatedRank" in query


def test_discover_teams_uses_per_league_language():
    client = WikidataClient(http=None)
    captured = {}

    def fake_run_query(sparql):
        captured["sparql"] = sparql
        return [
            {
                "team": {"value": "http://www.wikidata.org/entity/Q18500"},
                "teamLabel": {"value": "FC Basel"},
                "article": {"value": "https://de.wikipedia.org/wiki/FC_Basel"},
            }
        ]

    client.run_query = fake_run_query  # type: ignore[assignment]
    cfg = Config(language="en", leagues=[League(id="Q331268", language="de")])

    teams = client.discover_teams(cfg)

    assert "de.wikipedia.org" in captured["sparql"]
    assert teams[0].language == "de"
    assert teams[0].wikipedia_title == "FC Basel"
