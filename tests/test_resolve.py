from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.models import (
    QID_FROM_MEMBERSHIP,
    QID_FROM_SEARCH,
    Membership,
    PersonMatch,
    SquadPlayer,
    Team,
)
from wd_squads.resolve import (
    apply_person_matches,
    resolve_from_memberships,
    resolve_squad_qids,
    select_person_match,
    unresolved_names,
)


def _team():
    return Team(qid="Q1", label="FC Example", wikipedia_title="FC Example", language="de")


# --- pass 1: the team's own P54 statements ------------------------------------


def test_resolve_from_memberships_matches_on_name():
    # No article on Wikipedia, but Wikidata already has the membership.
    squad = [SquadPlayer(name="Kazeem Olaigbe", title="Kazeem Olaigbe", article_exists=False)]
    memberships = [
        Membership(
            "Q77",
            "Kazeem Olaigbe",
            "s1",
            start="2024-07-01",
            wikipedia_url="https://en.wikipedia.org/wiki/Kazeem_Olaigbe",
        )
    ]

    resolve_from_memberships(squad, memberships)

    assert squad[0].qid == "Q77"
    assert squad[0].qid_source == QID_FROM_MEMBERSHIP
    assert squad[0].wikipedia_url == "https://en.wikipedia.org/wiki/Kazeem_Olaigbe"


def test_resolve_from_memberships_ignores_case_and_spacing():
    squad = [SquadPlayer(name="  jonas  harder ")]
    resolve_from_memberships(squad, [Membership("Q5", "Jonas Harder", "s1")])
    assert squad[0].qid == "Q5"


def test_resolve_from_memberships_skips_ambiguous_names():
    # Two different items on this team share a label -> don't guess.
    squad = [SquadPlayer(name="Jonas Harder")]
    memberships = [
        Membership("Q5", "Jonas Harder", "s1"),
        Membership("Q6", "Jonas Harder", "s2"),
    ]
    resolve_from_memberships(squad, memberships)
    assert squad[0].qid is None


def test_resolve_from_memberships_never_reuses_a_claimed_qid():
    # A namesake already resolved via their article keeps the item to himself.
    squad = [
        SquadPlayer(name="Jonas Harder", title="Jonas Harder (Fußballspieler)", qid="Q5"),
        SquadPlayer(name="Jonas Harder"),
    ]
    resolve_from_memberships(squad, [Membership("Q5", "Jonas Harder", "s1")])
    assert squad[1].qid is None


def test_unresolved_names_lists_players_without_a_qid():
    squad = [
        SquadPlayer(name="Alice", qid="Q10"),
        SquadPlayer(name="Bob"),
        SquadPlayer(name="Bob"),  # duplicate collapses
    ]
    assert unresolved_names(squad) == ["Bob"]


# --- pass 2: Wikidata name search ---------------------------------------------


def test_select_person_match_prefers_the_candidate_already_on_the_team():
    candidates = [
        PersonMatch(name="Sam Smith", qid="Q1", label="Sam Smith"),
        PersonMatch(name="Sam Smith", qid="Q2", label="Sam Smith", at_team=True),
    ]
    match = select_person_match(candidates)
    assert match is not None and match.qid == "Q2"


def test_select_person_match_takes_a_lone_candidate():
    candidates = [PersonMatch(name="Sam Smith", qid="Q1", label="Sam Smith")]
    assert select_person_match(candidates).qid == "Q1"


def test_select_person_match_refuses_to_guess_between_namesakes():
    candidates = [
        PersonMatch(name="Sam Smith", qid="Q1", label="Sam Smith"),
        PersonMatch(name="Sam Smith", qid="Q2", label="Sam Smith"),
    ]
    assert select_person_match(candidates) is None
    assert select_person_match([]) is None


def test_apply_person_matches_fills_qid_and_article_link():
    squad = [SquadPlayer(name="Kazeem Olaigbe", title="Kazeem Olaigbe", article_exists=False)]
    matches = {
        "Kazeem Olaigbe": [
            PersonMatch(
                name="Kazeem Olaigbe",
                qid="Q77",
                label="Kazeem Olaigbe",
                wikipedia_url="https://en.wikipedia.org/wiki/Kazeem_Olaigbe",
            )
        ]
    }

    apply_person_matches(squad, matches)

    assert squad[0].qid == "Q77"
    assert squad[0].qid_source == QID_FROM_SEARCH
    assert squad[0].wikipedia_url == "https://en.wikipedia.org/wiki/Kazeem_Olaigbe"


def test_apply_person_matches_leaves_ambiguous_players_unresolved():
    squad = [SquadPlayer(name="Sam Smith")]
    matches = {
        "Sam Smith": [
            PersonMatch(name="Sam Smith", qid="Q1", label="Sam Smith"),
            PersonMatch(name="Sam Smith", qid="Q2", label="Sam Smith"),
        ]
    }
    apply_person_matches(squad, matches)
    assert squad[0].qid is None
    assert squad[0].qid_source is None


# --- both passes together ------------------------------------------------------


class FakeWikidata:
    def __init__(self, matches=None, error=None):
        self.matches = matches or {}
        self.error = error
        self.searched = None

    def search_people(self, names, team_qid, language="en"):
        self.searched = (list(names), team_qid, language)
        if self.error:
            raise self.error
        return self.matches


def test_resolve_squad_qids_only_searches_what_memberships_could_not_resolve():
    squad = [
        SquadPlayer(name="Alice", title="Alice", qid="Q10"),
        SquadPlayer(name="Bob"),  # has a membership already
        SquadPlayer(name="Carol"),  # only findable by search
    ]
    memberships = [Membership("Q11", "Bob", "s1")]
    wikidata = FakeWikidata(
        matches={"Carol": [PersonMatch(name="Carol", qid="Q12", label="Carol")]}
    )

    resolve_squad_qids(squad, memberships, wikidata, _team())

    assert wikidata.searched == (["Carol"], "Q1", "de")
    assert [p.qid for p in squad] == ["Q10", "Q11", "Q12"]


def test_resolve_squad_qids_survives_a_failing_search():
    squad = [SquadPlayer(name="Carol")]
    wikidata = FakeWikidata(error=RuntimeError("WDQS timeout"))

    resolve_squad_qids(squad, [], wikidata, _team())

    assert squad[0].qid is None  # reported as "no item", not as a crashed team
