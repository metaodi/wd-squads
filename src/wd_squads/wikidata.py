"""Query Wikidata (WDQS) for teams and their membership statements."""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from .config import Config
from .http_client import HttpClient
from .models import Membership, Team

log = logging.getLogger(__name__)

WDQS_ENDPOINT = "https://query.wikidata.org/sparql"
ENTITY_RE = re.compile(r"/entity/(Q\d+)$")
ARTICLE_TITLE_RE = re.compile(r"https://en\.wikipedia\.org/wiki/(.+)$")


def qid_from_uri(uri: str) -> Optional[str]:
    m = ENTITY_RE.search(uri or "")
    return m.group(1) if m else None


def _title_from_article_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = ARTICLE_TITLE_RE.match(url)
    if not m:
        return None
    from urllib.parse import unquote

    return unquote(m.group(1)).replace("_", " ")


class WikidataClient:
    def __init__(self, http: HttpClient, endpoint: str = WDQS_ENDPOINT) -> None:
        self.http = http
        self.endpoint = endpoint

    def run_query(self, sparql: str) -> List[dict]:
        """Run a SPARQL SELECT and return the list of binding rows."""
        data = self.http.get_json(
            self.endpoint,
            params={"query": sparql, "format": "json"},
            accept="application/sparql-results+json",
        )
        return data.get("results", {}).get("bindings", [])

    # -- team discovery ------------------------------------------------------
    def discover_teams(self, config: Config) -> List[Team]:
        if config.has_explicit_teams():
            return self._teams_from_qids(config.teams)
        if config.discovery_query:
            return self._teams_from_query(config.discovery_query)
        teams: List[Team] = []
        seen: set[str] = set()
        for league in config.leagues:
            for team in self._teams_from_query(self._league_query(league.id)):
                if team.qid not in seen:
                    seen.add(team.qid)
                    teams.append(team)
        return teams

    @staticmethod
    def _league_query(league_qid: str) -> str:
        # Association football club (Q476028) that has this league as its
        # `league` (P118) value, with the English Wikipedia article if any.
        return f"""
SELECT ?team ?teamLabel ?article WHERE {{
  ?team wdt:P118 wd:{league_qid} .
  ?team wdt:P31/wdt:P279* wd:Q476028 .
  OPTIONAL {{ ?article schema:about ?team ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY ?teamLabel
""".strip()

    @staticmethod
    def _values_query(qids: List[str]) -> str:
        values = " ".join(f"wd:{q}" for q in qids)
        return f"""
SELECT ?team ?teamLabel ?article WHERE {{
  VALUES ?team {{ {values} }}
  OPTIONAL {{ ?article schema:about ?team ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY ?teamLabel
""".strip()

    def _teams_from_qids(self, qids: List[str]) -> List[Team]:
        return self._teams_from_query(self._values_query(qids))

    def _teams_from_query(self, sparql: str) -> List[Team]:
        teams: List[Team] = []
        seen: set[str] = set()
        for row in self.run_query(sparql):
            qid = qid_from_uri(row.get("team", {}).get("value", ""))
            if not qid or qid in seen:
                continue
            seen.add(qid)
            label = row.get("teamLabel", {}).get("value", qid)
            title = _title_from_article_url(row.get("article", {}).get("value"))
            teams.append(Team(qid=qid, label=label, wikipedia_title=title))
        return teams

    # -- memberships ---------------------------------------------------------
    def get_memberships(self, team_qid: str) -> List[Membership]:
        """Return every P54 statement pointing at ``team_qid``.

        Includes open (no end date) and closed statements, so the diff can
        tell "add end date" apart from "review a closed membership".
        """
        sparql = f"""
SELECT ?player ?playerLabel ?statement ?start ?end WHERE {{
  ?statement ps:P54 wd:{team_qid} .
  ?player p:P54 ?statement .
  OPTIONAL {{ ?statement pq:P580 ?start . }}
  OPTIONAL {{ ?statement pq:P582 ?end . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
""".strip()
        memberships: List[Membership] = []
        for row in self.run_query(sparql):
            player_qid = qid_from_uri(row.get("player", {}).get("value", ""))
            if not player_qid:
                continue
            memberships.append(
                Membership(
                    player_qid=player_qid,
                    player_label=row.get("playerLabel", {}).get("value", player_qid),
                    statement_id=row.get("statement", {}).get("value", ""),
                    start=_date_value(row.get("start")),
                    end=_date_value(row.get("end")),
                )
            )
        return memberships


def _date_value(binding: Optional[dict]) -> Optional[str]:
    """Extract a short ISO date (YYYY[-MM[-DD]]) from a WDQS time binding."""
    if not binding:
        return None
    value = binding.get("value", "")
    if not value:
        return None
    # WDQS returns e.g. "2021-07-01T00:00:00Z"; keep the date part.
    return value.split("T", 1)[0].lstrip("+") or None
