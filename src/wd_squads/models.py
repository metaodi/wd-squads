"""Dataclasses shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --- Suggestion kinds -------------------------------------------------------
# Each suggestion has a ``kind`` from this list. ``PRIORITY`` maps the kind to a
# sort weight (lower = more important / more likely a real problem).
KIND_REVIEW_ENDED = "REVIEW_ENDED"
KIND_ADD_MEMBERSHIP = "ADD_MEMBERSHIP"
KIND_ADD_END_DATE = "ADD_END_DATE"
KIND_ADD_START_DATE = "ADD_START_DATE"
KIND_NO_WIKIDATA_ITEM = "NO_WIKIDATA_ITEM"

PRIORITY = {
    KIND_REVIEW_ENDED: 1,
    KIND_ADD_END_DATE: 2,
    KIND_ADD_MEMBERSHIP: 2,
    KIND_ADD_START_DATE: 3,
    KIND_NO_WIKIDATA_ITEM: 4,
}

# Human readable, one-line explanation of every kind (used in reports).
KIND_LABEL = {
    KIND_REVIEW_ENDED: "Membership marked ended, but player is in the current squad",
    KIND_ADD_MEMBERSHIP: "In current squad, but no membership statement on Wikidata",
    KIND_ADD_END_DATE: "Recorded as a current member, but no longer in the squad",
    KIND_ADD_START_DATE: "Current member, but the membership has no start date",
    KIND_NO_WIKIDATA_ITEM: "In current squad, but the Wikipedia article has no Wikidata item",
}


@dataclass
class Team:
    """A sports team we compare across the two projects."""

    qid: str
    label: str
    wikipedia_title: Optional[str] = None
    language: str = "en"  # Wikipedia edition its squad is read from
    league: Optional[str] = None  # league label, when discovered via config.leagues


@dataclass
class SquadPlayer:
    """A player read from a Wikipedia squad list.

    Sourced from an English-style {{fs player}} template or a German-style
    {{PersonZelle}} table cell; see ``wikipedia.parse_squad_players``.
    """

    name: str
    title: Optional[str] = None  # Wikipedia article title (from the wikilink)
    qid: Optional[str] = None  # resolved Wikidata Q-ID
    number: Optional[str] = None  # shirt number
    position: Optional[str] = None
    section: Optional[str] = None  # heading the player was listed under


@dataclass
class CareerSpell:
    """One club spell read from a player's own Wikipedia infobox.

    Sourced from the English ``{{Infobox football biography}}`` (``yearsN``/
    ``clubsN``) or German ``{{Infobox Fußballspieler}}`` (``vereine_tabelle``
    of ``{{Team-Station}}`` calls) formats; see
    ``wikipedia.parse_career_spells``.
    """

    club_name: str
    club_title: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None  # None + ongoing=True means still active
    ongoing: bool = False
    loan: bool = False


@dataclass
class Membership:
    """A P54 (member of sports team) statement on Wikidata."""

    player_qid: str
    player_label: str
    statement_id: str
    start: Optional[str] = None  # P580, ISO date string
    end: Optional[str] = None  # P582, ISO date string
    wikipedia_url: Optional[str] = None  # sitelink read off the Wikidata item

    @property
    def is_open(self) -> bool:
        """True when the membership has no end date (i.e. still current)."""
        return not self.end


@dataclass
class Suggestion:
    """A single suggested edit for a Wikidata user to review."""

    kind: str
    team: Team
    player_label: str
    detail: str
    player_qid: Optional[str] = None
    wikipedia_title: Optional[str] = None
    links: dict = field(default_factory=dict)
    # Possible start/end year for the membership, read off the player's own
    # Wikipedia infobox career history when available (see
    # ``diff.enrich_career_years``). A club spell still in progress leaves
    # ``end_year`` unset.
    start_year: Optional[int] = None
    end_year: Optional[int] = None

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.kind, 99)

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def years_label(self) -> str:
        """Human-readable "2020–2023" / "2020–" / "2020" / "" label."""
        if self.start_year and self.end_year:
            if self.start_year == self.end_year:
                return str(self.start_year)
            return f"{self.start_year}–{self.end_year}"
        if self.start_year:
            return f"{self.start_year}–"
        if self.end_year:
            return f"–{self.end_year}"
        return ""
