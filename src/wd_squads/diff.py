"""Compare a Wikipedia squad with Wikidata memberships and suggest edits."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional
from urllib.parse import unquote

from .models import (
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

_WIKIPEDIA_URL_RE = re.compile(r"^https://[a-z-]+\.wikipedia\.org/wiki/(.+)$")


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


# --- Career-year enrichment --------------------------------------------------
#
# compute_suggestions above only compares squad membership; the possible
# start/end year for a suggestion comes from a second pass, since it needs a
# per-player Wikipedia fetch (wikipedia.get_career_spells) that would be
# wasteful to run for the whole squad up front. suggestion_titles picks out
# which articles are worth fetching; enrich_career_years fills the years back
# in once they're fetched. Both are pure (no network of their own).


def _normalise_title(text: str) -> str:
    return text.replace("_", " ").strip().lower()


def _title_from_wikipedia_link(url: Optional[str]) -> Optional[str]:
    """Extract the article title from a Wikipedia URL, any language edition."""
    if not url:
        return None
    m = _WIKIPEDIA_URL_RE.match(url)
    if not m:
        return None
    return unquote(m.group(1)).replace("_", " ")


def _suggestion_title(s: Suggestion) -> Optional[str]:
    return s.wikipedia_title or _title_from_wikipedia_link(s.links.get("wikipedia"))


def suggestion_titles(suggestions: List[Suggestion]) -> List[str]:
    """Wikipedia article titles referenced by ``suggestions``, deduplicated.

    Meant to drive a follow-up ``WikipediaClient.get_career_spells`` call: we
    only want to fetch player biographies for players a suggestion is already
    being made about, not the whole squad.
    """
    titles: List[str] = []
    seen: set[str] = set()
    for s in suggestions:
        title = _suggestion_title(s)
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def select_team_spell(spells: List[CareerSpell], team: Team) -> Optional[CareerSpell]:
    """Pick the spell (if any) in ``spells`` that belongs to ``team``.

    Matches the wikilinked club article title against the team's own article
    title first (most reliable), falling back to a plain-text club name
    equal to the team's label — some spells (e.g. a player who returned to a
    club already linked earlier in their infobox) are written as plain text
    the second time round. When several spells match (left and came back),
    the still-open one is preferred, else the most recent one.
    """
    team_title = _normalise_title(team.wikipedia_title) if team.wikipedia_title else None
    team_label = _normalise_title(team.label) if team.label else None

    def matches(spell: CareerSpell) -> bool:
        club_title = _normalise_title(spell.club_title) if spell.club_title else None
        if club_title and team_title and club_title == team_title:
            return True
        if club_title and team_label and club_title == team_label:
            return True
        if team_label and _normalise_title(spell.club_name) == team_label:
            return True
        return False

    candidates = [s for s in spells if matches(s)]
    if not candidates:
        return None
    ongoing = [s for s in candidates if s.ongoing]
    if ongoing:
        return ongoing[0]
    return max(candidates, key=lambda s: (s.end_year or s.start_year or 0, s.start_year or 0))


def enrich_career_years(
    suggestions: List[Suggestion],
    career: Dict[str, List[CareerSpell]],
    team: Team,
) -> None:
    """Fill in ``start_year``/``end_year`` on ``suggestions`` in place.

    ``career`` maps a Wikipedia article title to that player's parsed career
    spells (from ``WikipediaClient.get_career_spells``); a suggestion whose
    player has no matching spell for ``team`` is left untouched.
    """
    for s in suggestions:
        title = _suggestion_title(s)
        if not title:
            continue
        spell = select_team_spell(career.get(title, []), team)
        if spell:
            s.start_year = spell.start_year
            s.end_year = spell.end_year
