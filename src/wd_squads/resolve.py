"""Find the Wikidata item behind a squad player, with or without an article.

``WikipediaClient.get_squad`` can only resolve a player whose Wikipedia article
exists *and* is connected to Wikidata. That leaves out a large group — squad
members who simply have no article in that edition (a red link, or no link at
all) — even though most of them do have a Wikidata item, reachable by name.

This module closes that gap in two passes, cheapest first:

1. :func:`resolve_from_memberships` — match the name against the team's own P54
   statements, which we already fetched. Free, and the strongest signal there
   is: Wikidata already says this person plays here.
2. :func:`apply_person_matches` — match the name against item labels/aliases
   found by :meth:`WikidataClient.search_people`.

Both are pure; :func:`resolve_squad_qids` wires them around the one network
call. Every match they make is by *name*, so the Q-ID gets a ``qid_source``
marking it as a guess, and the reports ask the reader to verify the identity.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional

from .models import (
    QID_FROM_MEMBERSHIP,
    QID_FROM_SEARCH,
    Membership,
    PersonMatch,
    SquadPlayer,
    Team,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .wikidata import WikidataClient

log = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalise_name(name: str) -> str:
    return _WHITESPACE_RE.sub(" ", (name or "").strip()).casefold()


def _claimed_qids(squad: List[SquadPlayer]) -> set:
    return {p.qid for p in squad if p.qid}


def resolve_from_memberships(
    squad: List[SquadPlayer], memberships: List[Membership]
) -> None:
    """Fill in Q-IDs from the team's P54 statements, matching on player name.

    A squad player with no article but an existing membership statement would
    otherwise be reported twice over — once as "no Wikidata item", once as a
    member Wikipedia has dropped — when in truth there is nothing to do.

    Ambiguous names (two items on this team labelled the same) are left alone.
    """
    by_name: Dict[str, set] = defaultdict(set)
    labels: Dict[str, str] = {}
    for m in memberships:
        key = _normalise_name(m.player_label)
        if not key:
            continue
        by_name[key].add(m.player_qid)
        labels[m.player_qid] = m.player_label

    urls = {
        m.player_qid: m.wikipedia_url for m in memberships if m.wikipedia_url
    }
    taken = _claimed_qids(squad)
    for player in squad:
        if player.qid:
            continue
        qids = by_name.get(_normalise_name(player.name), set()) - taken
        if len(qids) != 1:
            continue
        qid = qids.pop()
        player.qid = qid
        player.qid_source = QID_FROM_MEMBERSHIP
        player.wikipedia_url = player.wikipedia_url or urls.get(qid)
        taken.add(qid)


def unresolved_names(squad: List[SquadPlayer]) -> List[str]:
    """Names of squad players still without a Q-ID, deduplicated."""
    return list(
        dict.fromkeys(p.name.strip() for p in squad if not p.qid and p.name.strip())
    )


def select_person_match(candidates: List[PersonMatch]) -> Optional[PersonMatch]:
    """Pick the item a searched name refers to, or ``None`` if unclear.

    A candidate that already has a P54 statement for the team wins outright.
    Otherwise the name must identify exactly one person: guessing between
    namesakes would put a wrong Q-ID in front of a human editor, which is worse
    than reporting nothing.
    """
    if not candidates:
        return None
    at_team = [c for c in candidates if c.at_team]
    if len(at_team) == 1:
        return at_team[0]
    if not at_team and len(candidates) == 1:
        return candidates[0]
    return None


def apply_person_matches(
    squad: List[SquadPlayer], matches: Dict[str, List[PersonMatch]]
) -> None:
    """Fill in Q-IDs from ``WikidataClient.search_people`` results, in place."""
    by_name: Dict[str, List[PersonMatch]] = defaultdict(list)
    for name, candidates in matches.items():
        by_name[_normalise_name(name)].extend(candidates)

    taken = _claimed_qids(squad)
    for player in squad:
        if player.qid:
            continue
        candidates = [
            c for c in by_name.get(_normalise_name(player.name), []) if c.qid not in taken
        ]
        match = select_person_match(candidates)
        if not match:
            continue
        player.qid = match.qid
        player.qid_source = QID_FROM_SEARCH
        player.wikipedia_url = player.wikipedia_url or match.wikipedia_url
        taken.add(match.qid)


def resolve_squad_qids(
    squad: List[SquadPlayer],
    memberships: List[Membership],
    wikidata: "WikidataClient",
    team: Team,
) -> None:
    """Run both name-resolution passes over ``squad``, in place.

    The search is a best-effort extra: if WDQS refuses it (a timeout on a large
    squad, say), the players it would have resolved simply stay unresolved
    instead of failing the whole team.
    """
    resolve_from_memberships(squad, memberships)
    names = unresolved_names(squad)
    if not names:
        return
    try:
        matches = wikidata.search_people(names, team.qid, team.language)
    except Exception as exc:  # non-fatal: report the rest of the team anyway
        log.warning("Name search failed for %s (%s): %s", team.label, team.qid, exc)
        return
    apply_person_matches(squad, matches)
