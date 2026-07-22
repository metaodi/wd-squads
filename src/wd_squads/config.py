"""Load and validate the YAML configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


DEFAULT_TEAM_CLASS = "Q476028"  # association football club


@dataclass
class League:
    id: str
    label: Optional[str] = None
    language: Optional[str] = None  # Wikipedia edition; falls back to Config.language
    team_class: Optional[str] = None  # Wikidata class teams must be an instance of;
    # falls back to Config.team_class. Lets a league discover a different kind of
    # team (e.g. an ice hockey league using "ice hockey team" instead of the
    # football default) without any code change.


@dataclass
class Config:
    language: str = "en"
    user_agent: str = "wd-squads/0.1 (+https://github.com/metaodi/wd-squads)"
    request_delay: float = 1.0
    team_class: str = DEFAULT_TEAM_CLASS
    leagues: List[League] = field(default_factory=list)
    discovery_query: Optional[str] = None
    teams: List[str] = field(default_factory=list)

    def has_explicit_teams(self) -> bool:
        return bool(self.teams)


def load_config(path: str | Path) -> Config:
    """Read a YAML config file into a :class:`Config`."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    default_language = data.get("language", "en")
    default_team_class = data.get("team_class", DEFAULT_TEAM_CLASS)
    leagues = [
        League(
            id=str(item["id"]),
            label=item.get("label"),
            language=item.get("language", default_language),
            team_class=item.get("team_class", default_team_class),
        )
        if isinstance(item, dict)
        else League(id=str(item), language=default_language, team_class=default_team_class)
        for item in (data.get("leagues") or [])
    ]

    cfg = Config(
        language=default_language,
        user_agent=data.get("user_agent", Config.user_agent),
        request_delay=float(data.get("request_delay", 1.0)),
        team_class=default_team_class,
        leagues=leagues,
        discovery_query=data.get("discovery_query"),
        teams=[str(t) for t in (data.get("teams") or [])],
    )

    if not cfg.leagues and not cfg.discovery_query and not cfg.teams:
        raise ValueError(
            "Config must define at least one of: 'leagues', 'discovery_query' "
            "or 'teams'."
        )
    if not cfg.user_agent or "example.com" in cfg.user_agent:
        raise ValueError(
            "Please set a descriptive 'user_agent' with a contact URL/e-mail; "
            "the Wikimedia APIs require it."
        )
    return cfg
