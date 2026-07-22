from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.config import Config, League
from wd_squads.wikidata import WikidataClient, _title_from_article_url


def test_title_from_article_url_respects_language():
    de = "https://de.wikipedia.org/wiki/FC_Basel"
    assert _title_from_article_url(de, "de") == "FC Basel"
    # A URL from a different edition than expected is ignored.
    assert _title_from_article_url(de, "en") is None


def test_get_memberships_splits_labels_into_a_separate_query():
    client = WikidataClient(http=None)
    queries = []

    def fake_run_query(sparql):
        queries.append(sparql)
        if "ps:P54" in sparql:
            # The statement query must NOT carry the label service, otherwise
            # the combined result grows large enough for WDQS to truncate it.
            assert "wikibase:label" not in sparql
            return [
                {
                    "player": {"value": "http://www.wikidata.org/entity/Q10"},
                    "statement": {"value": "stmt-1"},
                    "start": {"value": "2020-01-01T00:00:00Z"},
                }
            ]
        # The label lookup is a lean VALUES query.
        assert "VALUES ?player" in sparql
        return [
            {
                "player": {"value": "http://www.wikidata.org/entity/Q10"},
                "playerLabel": {"value": "Alice Example"},
            }
        ]

    client.run_query = fake_run_query  # type: ignore[assignment]

    memberships = client.get_memberships("Q1")

    assert len(queries) == 2
    assert len(memberships) == 1
    assert memberships[0].player_qid == "Q10"
    assert memberships[0].player_label == "Alice Example"
    assert memberships[0].start == "2020-01-01"
    assert memberships[0].is_open


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
