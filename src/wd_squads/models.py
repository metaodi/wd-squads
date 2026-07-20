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
    """A football club we compare across the two projects."""

    qid: str
    label: str
    wikipedia_title: Optional[str] = None
    language: str = "en"  # Wikipedia edition its squad is read from


@dataclass
class SquadPlayer:
    """A player read from a {{fs player}} template on Wikipedia."""

    name: str
    title: Optional[str] = None  # Wikipedia article title (from the wikilink)
    qid: Optional[str] = None  # resolved Wikidata Q-ID
    number: Optional[str] = None  # shirt number
    position: Optional[str] = None
    section: Optional[str] = None  # heading the player was listed under


@dataclass
class Membership:
    """A P54 (member of sports team) statement on Wikidata."""

    player_qid: str
    player_label: str
    statement_id: str
    start: Optional[str] = None  # P580, ISO date string
    end: Optional[str] = None  # P582, ISO date string

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

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.kind, 99)

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)
