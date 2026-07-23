from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.diff import (
    compute_suggestions,
    enrich_career_years,
    select_team_spell,
    suggestion_titles,
)
from wd_squads.models import (
    KIND_ADD_END_DATE,
    KIND_ADD_MEMBERSHIP,
    KIND_ADD_START_DATE,
    KIND_NO_WIKIDATA_ITEM,
    KIND_REVIEW_ENDED,
    CareerSpell,
    Membership,
    SquadPlayer,
    Suggestion,
    Team,
)


def _team():
    return Team(qid="Q1", label="FC Example", wikipedia_title="FC Example")


def test_full_diff_matrix():
    squad = [
        SquadPlayer(name="Alice", title="Alice", qid="Q10"),   # ok
        SquadPlayer(name="Bob", title="Bob", qid="Q11"),       # open, no start
        SquadPlayer(name="Eve", title="Eve", qid="Q12"),       # no membership
        SquadPlayer(name="Frank", title="Frank", qid=None),    # no wikidata item
        SquadPlayer(name="Gina", title="Gina", qid="Q13"),     # only closed
    ]
    memberships = [
        Membership("Q10", "Alice", "s1", start="2020-01-01", end=None),
        Membership("Q11", "Bob", "s2", start=None, end=None),
        Membership("Q13", "Gina", "s3", start="2015-01-01", end="2019-01-01"),
        Membership("Q99", "Zoe", "s4", start="2018-01-01", end=None),  # left club
    ]

    suggestions = compute_suggestions(_team(), squad, memberships)
    kinds = {(s.player_label, s.kind) for s in suggestions}

    assert ("Bob", KIND_ADD_START_DATE) in kinds
    assert ("Eve", KIND_ADD_MEMBERSHIP) in kinds
    assert ("Frank", KIND_NO_WIKIDATA_ITEM) in kinds
    assert ("Gina", KIND_REVIEW_ENDED) in kinds
    assert ("Zoe", KIND_ADD_END_DATE) in kinds
    # Alice is fully in sync -> no suggestion for her.
    assert not any(s.player_label == "Alice" for s in suggestions)
    assert len(suggestions) == 5


def test_sorted_by_priority():
    squad = [SquadPlayer(name="Eve", title="Eve", qid="Q12")]
    memberships = [Membership("Q99", "Zoe", "s4", end=None)]
    suggestions = compute_suggestions(_team(), squad, memberships)
    priorities = [s.priority for s in suggestions]
    assert priorities == sorted(priorities)


def test_open_membership_with_start_is_clean():
    squad = [SquadPlayer(name="Alice", title="Alice", qid="Q10")]
    memberships = [Membership("Q10", "Alice", "s1", start="2020-01-01", end=None)]
    assert compute_suggestions(_team(), squad, memberships) == []


def test_add_end_date_includes_wikipedia_link_from_sitelink():
    squad = [SquadPlayer(name="Eve", title="Eve", qid="Q12")]
    memberships = [
        Membership(
            "Q99",
            "Zoe",
            "s4",
            start="2018-01-01",
            end=None,
            wikipedia_url="https://en.wikipedia.org/wiki/Zoe",
        )
    ]
    suggestions = compute_suggestions(_team(), squad, memberships)
    zoe = next(s for s in suggestions if s.player_label == "Zoe")
    assert zoe.links["wikipedia"] == "https://en.wikipedia.org/wiki/Zoe"
    assert zoe.links["item"] == "https://www.wikidata.org/wiki/Q99"


# --- Career-year enrichment ---------------------------------------------------


def test_select_team_spell_matches_by_wikilink_title():
    team = Team(qid="Q1", label="FC Example", wikipedia_title="FC Example FC")
    spells = [
        CareerSpell(club_name="Other Club", club_title="Other Club", start_year=2010, end_year=2012),
        CareerSpell(club_name="FC Example", club_title="FC Example FC", start_year=2015, end_year=2018),
    ]
    spell = select_team_spell(spells, team)
    assert spell is not None
    assert spell.start_year == 2015
    assert spell.end_year == 2018


def test_select_team_spell_falls_back_to_plain_text_name():
    # A repeat spell with no wikilink (e.g. German infobox's second stint)
    # must still match by comparing the display text to the team's label.
    team = Team(qid="Q1", label="FC Zürich", wikipedia_title="FC Zürich")
    spells = [CareerSpell(club_name="FC Zürich", club_title=None, start_year=2013, end_year=2019)]
    spell = select_team_spell(spells, team)
    assert spell is not None
    assert spell.start_year == 2013


def test_select_team_spell_prefers_ongoing_over_past_spells():
    team = Team(qid="Q1", label="FC Example", wikipedia_title="FC Example")
    spells = [
        CareerSpell(club_name="FC Example", club_title="FC Example", start_year=2015, end_year=2016),
        CareerSpell(club_name="FC Example", club_title="FC Example", start_year=2022, end_year=None, ongoing=True),
    ]
    spell = select_team_spell(spells, team)
    assert spell is not None
    assert spell.start_year == 2022
    assert spell.ongoing is True


def test_select_team_spell_no_match_returns_none():
    team = Team(qid="Q1", label="FC Example", wikipedia_title="FC Example")
    spells = [CareerSpell(club_name="Some Other Club", club_title="Some Other Club", start_year=2015, end_year=2018)]
    assert select_team_spell(spells, team) is None


def test_suggestion_titles_collects_wikipedia_title_and_link_fallback():
    suggestions = [
        Suggestion(
            kind=KIND_ADD_MEMBERSHIP,
            team=_team(),
            player_label="Eve",
            wikipedia_title="Eve",
            detail="",
        ),
        Suggestion(
            kind=KIND_ADD_END_DATE,
            team=_team(),
            player_label="Zoe",
            detail="",
            links={"wikipedia": "https://en.wikipedia.org/wiki/Zoe_Player"},
        ),
        # No title and no wikipedia link -> excluded.
        Suggestion(kind=KIND_NO_WIKIDATA_ITEM, team=_team(), player_label="Nameless", detail=""),
    ]
    assert suggestion_titles(suggestions) == ["Eve", "Zoe Player"]


def test_enrich_career_years_fills_in_matching_suggestion():
    team = _team()  # wikipedia_title="FC Example"
    suggestion = Suggestion(
        kind=KIND_ADD_MEMBERSHIP,
        team=team,
        player_label="Eve",
        wikipedia_title="Eve",
        detail="",
    )
    career = {
        "Eve": [
            CareerSpell(club_name="FC Example", club_title="FC Example", start_year=2022, ongoing=True)
        ]
    }
    enrich_career_years([suggestion], career, team)
    assert suggestion.start_year == 2022
    assert suggestion.end_year is None
    assert suggestion.years_label == "2022–"


def test_enrich_career_years_leaves_unmatched_suggestion_alone():
    team = _team()
    suggestion = Suggestion(
        kind=KIND_ADD_MEMBERSHIP, team=team, player_label="Eve", wikipedia_title="Eve", detail=""
    )
    enrich_career_years([suggestion], {}, team)
    assert suggestion.start_year is None
    assert suggestion.end_year is None
