import json

from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.app import process
from wd_squads.config import Config
from wd_squads.models import Membership, SquadPlayer, Team
from wd_squads.report import write_reports


class FakeWikidata:
    def discover_teams(self, config):
        return [Team(qid="Q1", label="FC Example", wikipedia_title="FC Example")]

    def get_memberships(self, qid):
        return [
            Membership("Q10", "Alice", "s1", start="2020-01-01", end=None),
            Membership("Q99", "Zoe", "s4", start="2018-01-01", end=None),
        ]


class FakeWikipedia:
    def get_squad(self, team):
        return [
            SquadPlayer(name="Alice", title="Alice", qid="Q10"),
            SquadPlayer(name="Eve", title="Eve", qid="Q12"),
        ]


def test_process_and_write(tmp_path):
    config = Config(language="en")
    results = process(config, FakeWikidata(), FakeWikipedia())

    assert len(results) == 1
    result = results[0]
    assert result.squad_size == 2
    assert result.wikidata_current == 2  # Q10 + Q99 open
    # Eve needs a membership, Zoe needs an end date.
    kinds = {s.kind for s in result.suggestions}
    assert "ADD_MEMBERSHIP" in kinds
    assert "ADD_END_DATE" in kinds

    reports = tmp_path / "reports"
    docs = tmp_path / "docs"
    write_reports(results, reports, docs, generated_at="2026-07-20 00:00 UTC")

    assert (reports / "README.md").exists()
    assert (reports / "Q1-fc-example.md").exists()
    assert (docs / "index.html").exists()

    data = json.loads((docs / "data.json").read_text(encoding="utf-8"))
    assert data["total_suggestions"] == len(result.suggestions)
    assert data["teams"][0]["qid"] == "Q1"

    html = (docs / "index.html").read_text(encoding="utf-8")
    assert "FC Example" in html
    assert "wd-squads" in html
