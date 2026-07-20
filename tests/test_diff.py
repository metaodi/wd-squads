from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.diff import compute_suggestions
from wd_squads.models import (
    KIND_ADD_END_DATE,
    KIND_ADD_MEMBERSHIP,
    KIND_ADD_START_DATE,
    KIND_NO_WIKIDATA_ITEM,
    KIND_REVIEW_ENDED,
    Membership,
    SquadPlayer,
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
