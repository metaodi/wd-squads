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


def test_people_search_query_is_narrow_on_purpose():
    query = WikidataClient._people_search_query(["Kazeem Olaigbe"], "Q18500", "de")

    # Exact label/alias match in the squad's language, plus English and the
    # language-agnostic "mul" label.
    assert '"Kazeem Olaigbe"@de' in query
    assert '"Kazeem Olaigbe"@en' in query
    assert '"Kazeem Olaigbe"@mul' in query
    assert "rdfs:label ?name" in query
    assert "skos:altLabel ?name" in query

    # Only humans, and only ones who plausibly play a sport.
    assert "wdt:P31 wd:Q5" in query
    assert "wdt:P106/wdt:P279* wd:Q2066131" in query
    assert "wdt:P54 ?anyTeam" in query

    # A candidate already on this team is flagged, to settle namesakes.
    assert "EXISTS { ?player wdt:P54 wd:Q18500 }" in query


def test_people_search_query_escapes_quotes_in_a_name():
    query = WikidataClient._people_search_query(['Ars"ne'], "Q1", "en")
    assert '"Ars\\"ne"@en' in query


def test_search_people_groups_candidates_and_skips_one_word_names():
    client = WikidataClient(http=None)
    captured = {}

    def fake_run_query(sparql):
        captured["sparql"] = sparql
        return [
            {
                "name": {"value": "Sam Smith", "xml:lang": "de"},
                "player": {"value": "http://www.wikidata.org/entity/Q1"},
                "playerLabel": {"value": "Sam Smith"},
                "atTeam": {"value": "false"},
            },
            {  # same item, matched again via its English label
                "name": {"value": "Sam Smith", "xml:lang": "en"},
                "player": {"value": "http://www.wikidata.org/entity/Q1"},
                "playerLabel": {"value": "Sam Smith"},
                "atTeam": {"value": "false"},
            },
            {
                "name": {"value": "Sam Smith", "xml:lang": "en"},
                "player": {"value": "http://www.wikidata.org/entity/Q2"},
                "playerLabel": {"value": "Sam Smith"},
                "atTeam": {"value": "true"},
                "articleEn": {"value": "https://en.wikipedia.org/wiki/Sam_Smith"},
            },
        ]

    client.run_query = fake_run_query  # type: ignore[assignment]

    matches = client.search_people(["Sam Smith", "Rodri"], "Q1", language="de")

    # A single-word name is too likely to collide -> never searched.
    assert "Rodri" not in captured["sparql"]
    candidates = matches["Sam Smith"]
    assert [c.qid for c in candidates] == ["Q1", "Q2"]  # deduplicated per item
    assert candidates[1].at_team is True
    assert candidates[1].wikipedia_url == "https://en.wikipedia.org/wiki/Sam_Smith"


def test_search_people_makes_no_query_when_nothing_is_searchable():
    client = WikidataClient(http=None)

    def fail(sparql):  # pragma: no cover - must not be reached
        raise AssertionError("no query should be run")

    client.run_query = fail  # type: ignore[assignment]
    assert client.search_people(["Rodri", "", "  "], "Q1") == {}


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
