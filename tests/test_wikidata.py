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

    # Defaults to the football team class when none is given.
    assert "wdt:P31/wdt:P279* wd:Q476028" in query


def test_league_query_accepts_a_different_team_class():
    # A non-football team_class (e.g. for another sport) is used verbatim,
    # without touching any other part of the query.
    query = WikidataClient._league_query("Q331268", "de", team_class="Q999001")

    assert "wdt:P31/wdt:P279* wd:Q999001" in query
    assert "Q476028" not in query


def test_get_memberships_reads_sitelink_with_english_fallback():
    client = WikidataClient(http=None)
    captured = {}

    def fake_run_query(sparql):
        captured["sparql"] = sparql
        return [
            {
                "player": {"value": "http://www.wikidata.org/entity/Q10"},
                "playerLabel": {"value": "Alice"},
                "statement": {"value": "statement:s1"},
                "article": {"value": "https://de.wikipedia.org/wiki/Alice"},
            },
            {
                "player": {"value": "http://www.wikidata.org/entity/Q11"},
                "playerLabel": {"value": "Bob"},
                "statement": {"value": "statement:s2"},
                "articleEn": {"value": "https://en.wikipedia.org/wiki/Bob"},
            },
            {
                "player": {"value": "http://www.wikidata.org/entity/Q12"},
                "playerLabel": {"value": "Cara"},
                "statement": {"value": "statement:s3"},
            },
        ]

    client.run_query = fake_run_query  # type: ignore[assignment]

    memberships = client.get_memberships("Q1", language="de")

    assert "de.wikipedia.org" in captured["sparql"]
    assert "en.wikipedia.org" in captured["sparql"]
    by_qid = {m.player_qid: m for m in memberships}
    assert by_qid["Q10"].wikipedia_url == "https://de.wikipedia.org/wiki/Alice"
    # Falls back to the English sitelink when the requested language has none.
    assert by_qid["Q11"].wikipedia_url == "https://en.wikipedia.org/wiki/Bob"
    # No sitelink at all -> None, not an error.
    assert by_qid["Q12"].wikipedia_url is None


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
