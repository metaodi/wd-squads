"""Compare a Wikipedia squad with Wikidata memberships and suggest edits."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from .models import (
    KIND_ADD_END_DATE,
    KIND_ADD_MEMBERSHIP,
    KIND_ADD_START_DATE,
    KIND_NO_WIKIDATA_ITEM,
    KIND_REVIEW_ENDED,
    Membership,
    SquadPlayer,
    Suggestion,
    Team,
)


def _wikidata_item_url(qid: str) -> str:
    return f"https://www.wikidata.org/wiki/{qid}"


def _wikipedia_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}"


def compute_suggestions(
    team: Team,
    squad: List[SquadPlayer],
    memberships: List[Membership],
    language: Optional[str] = None,
) -> List[Suggestion]:
    """Produce the list of suggested edits for a single team."""
    language = language or team.language
    by_player: Dict[str, List[Membership]] = defaultdict(list)
    for m in memberships:
        by_player[m.player_qid].append(m)

    squad_qids = {p.qid for p in squad if p.qid}
    suggestions: List[Suggestion] = []

    # 1) Walk the Wikipedia squad and check each player against Wikidata.
    for player in squad:
        team_link = {"team": _wikidata_item_url(team.qid)}
        if player.title:
            team_link["wikipedia"] = _wikipedia_url(language, player.title)

        if not player.qid:
            suggestions.append(
                Suggestion(
                    kind=KIND_NO_WIKIDATA_ITEM,
                    team=team,
                    player_label=player.name,
                    wikipedia_title=player.title,
                    detail=(
                        f"'{player.name}' is listed in the squad on Wikipedia but "
                        "its article has no linked Wikidata item."
                    ),
                    links=team_link,
                )
            )
            continue

        links = dict(team_link, item=_wikidata_item_url(player.qid))
        player_memberships = by_player.get(player.qid, [])
        open_memberships = [m for m in player_memberships if m.is_open]

        if not player_memberships:
            suggestions.append(
                Suggestion(
                    kind=KIND_ADD_MEMBERSHIP,
                    team=team,
                    player_label=player.name,
                    player_qid=player.qid,
                    wikipedia_title=player.title,
                    detail=(
                        f"Add a 'member of sports team' (P54) statement → {team.label} "
                        f"({team.qid}); the player is in the current squad on Wikipedia."
                    ),
                    links=links,
                )
            )
        elif open_memberships:
            # Currently a member on Wikidata; flag a missing start date.
            if all(not m.start for m in open_memberships):
                suggestions.append(
                    Suggestion(
                        kind=KIND_ADD_START_DATE,
                        team=team,
                        player_label=player.name,
                        player_qid=player.qid,
                        wikipedia_title=player.title,
                        detail=(
                            "Add a start date (P580) qualifier to the membership; it is "
                            "currently open but undated, which makes 'current squad' "
                            "queries unreliable."
                        ),
                        links=links,
                    )
                )
            # else: open membership with a start date -> nothing to do.
        else:
            # Only closed memberships exist, yet the player is in the squad.
            suggestions.append(
                Suggestion(
                    kind=KIND_REVIEW_ENDED,
                    team=team,
                    player_label=player.name,
                    player_qid=player.qid,
                    wikipedia_title=player.title,
                    detail=(
                        "Wikidata records this membership as ended (P582 set), but the "
                        "player is in the current squad on Wikipedia. They may have "
                        "returned, or the end date may be wrong."
                    ),
                    links=links,
                )
            )

    # 2) Players Wikidata thinks are current, but Wikipedia dropped them.
    for player_qid, player_memberships in by_player.items():
        if player_qid in squad_qids:
            continue
        open_memberships = [m for m in player_memberships if m.is_open]
        if not open_memberships:
            continue
        label = open_memberships[0].player_label
        links = {
            "item": _wikidata_item_url(player_qid),
            "team": _wikidata_item_url(team.qid),
        }
        wikipedia_url = next(
            (m.wikipedia_url for m in open_memberships if m.wikipedia_url), None
        )
        if wikipedia_url:
            links["wikipedia"] = wikipedia_url
        suggestions.append(
            Suggestion(
                kind=KIND_ADD_END_DATE,
                team=team,
                player_label=label,
                player_qid=player_qid,
                detail=(
                    f"Add an end date (P582) to the membership → {team.label} "
                    f"({team.qid}); Wikidata lists the player as a current member, but "
                    "they are no longer in the squad on Wikipedia."
                ),
                links=links,
            )
        )

    suggestions.sort(key=lambda s: (s.priority, s.player_label.lower()))
    return suggestions
