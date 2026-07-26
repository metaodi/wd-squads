"""Query Wikidata (WDQS) for teams and their membership statements."""

from __future__ import annotations

import logging
import re
from typing import Dict, Iterator, List, Optional

from .config import DEFAULT_TEAM_CLASS, Config
from .http_client import HttpClient
from .models import Membership, PersonMatch, Team

log = logging.getLogger(__name__)

WDQS_ENDPOINT = "https://query.wikidata.org/sparql"
ENTITY_RE = re.compile(r"/entity/(Q\d+)$")

# "athlete" — the superclass every sports occupation (association football
# player, ice hockey player, …) sits under. Used to keep the name search of
# ``search_people`` on people who plausibly play the sport.
ATHLETE_CLASS = "Q2066131"

# Label languages a player's name is looked up in, on top of the Wikipedia
# edition the squad was read from. "mul" is Wikidata's language-agnostic label
# (increasingly where a person's name lives, instead of being repeated per
# language); "en" is the most consistently filled edition-specific one.
EXTRA_LABEL_LANGUAGES = ("en", "mul")

# Names too short to be discriminating are never searched — a one-word name is
# far more likely to collide with an unrelated person.
_SEARCHABLE_NAME_RE = re.compile(r"\S+\s+\S+")

# Names per name-search query. Each one contributes a literal per label
# language, and the query travels in the URL of a GET, so this keeps the
# request comfortably under the usual ~8 KB header limit.
SEARCH_BATCH_SIZE = 30


def qid_from_uri(uri: str) -> Optional[str]:
    m = ENTITY_RE.search(uri or "")
    return m.group(1) if m else None


def _title_from_article_url(url: Optional[str], language: str) -> Optional[str]:
    if not url:
        return None
    prefix = f"https://{language}.wikipedia.org/wiki/"
    if not url.startswith(prefix):
        return None
    from urllib.parse import unquote

    return unquote(url[len(prefix) :]).replace("_", " ")


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
            return self._teams_from_qids(config.teams, config.language)
        if config.discovery_query:
            return self._teams_from_query(config.discovery_query, config.language)
        teams: List[Team] = []
        seen: set[str] = set()
        for league in config.leagues:
            language = league.language or config.language
            team_class = league.team_class or config.team_class
            query = self._league_query(league.id, language, team_class)
            for team in self._teams_from_query(
                query, language, league_label=league.label or league.id
            ):
                if team.qid not in seen:
                    seen.add(team.qid)
                    teams.append(team)
        return teams

    @staticmethod
    def _league_query(league_qid: str, language: str, team_class: str = DEFAULT_TEAM_CLASS) -> str:
        # A team of ``team_class`` (an instance of it, or a subclass thereof;
        # defaults to association football club, Q476028) whose `league` (P118)
        # is this league, with the article on the chosen Wikipedia. Passing a
        # different class (e.g. "ice hockey team") lets the same query work for
        # other sports without touching this code.
        #
        # We walk the statement node (p:/ps:) instead of the truthy predicate
        # (wdt:) so we can inspect qualifiers: a club whose league membership
        # carries an `end time` (P582) already in the past no longer competes
        # there and is excluded. Deprecated-rank statements are dropped too,
        # to keep the wdt: semantics we replaced.
        return f"""
SELECT ?team ?teamLabel ?article WHERE {{
  ?team p:P118 ?membership .
  ?membership ps:P118 wd:{league_qid} ;
              wikibase:rank ?rank .
  FILTER ( ?rank != wikibase:DeprecatedRank )
  FILTER NOT EXISTS {{
    ?membership pq:P582 ?end .
    FILTER ( ?end < NOW() )
  }}
  ?team wdt:P31/wdt:P279* wd:{team_class} .
  OPTIONAL {{ ?article schema:about ?team ; schema:isPartOf <https://{language}.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language},en". }}
}}
ORDER BY ?teamLabel
""".strip()

    @staticmethod
    def _values_query(qids: List[str], language: str) -> str:
        values = " ".join(f"wd:{q}" for q in qids)
        return f"""
SELECT ?team ?teamLabel ?article WHERE {{
  VALUES ?team {{ {values} }}
  OPTIONAL {{ ?article schema:about ?team ; schema:isPartOf <https://{language}.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language},en". }}
}}
ORDER BY ?teamLabel
""".strip()

    def _teams_from_qids(self, qids: List[str], language: str) -> List[Team]:
        return self._teams_from_query(self._values_query(qids, language), language)

    def _teams_from_query(
        self, sparql: str, language: str, league_label: Optional[str] = None
    ) -> List[Team]:
        teams: List[Team] = []
        seen: set[str] = set()
        for row in self.run_query(sparql):
            qid = qid_from_uri(row.get("team", {}).get("value", ""))
            if not qid or qid in seen:
                continue
            seen.add(qid)
            label = row.get("teamLabel", {}).get("value", qid)
            title = _title_from_article_url(row.get("article", {}).get("value"), language)
            teams.append(
                Team(
                    qid=qid,
                    label=label,
                    wikipedia_title=title,
                    language=language,
                    league=league_label,
                )
            )
        return teams

    # -- memberships ---------------------------------------------------------
    def get_memberships(self, team_qid: str, language: str = "en") -> List[Membership]:
        """Return every P54 statement pointing at ``team_qid``.

        Includes open (no end date) and closed statements, so the diff can
        tell "add end date" apart from "review a closed membership".

        Also reads the player's Wikipedia sitelink (in ``language`` first,
        falling back to English) so reports can link to the article even for
        players who are no longer in the Wikipedia squad list.
        """
        sparql = f"""
SELECT ?player ?playerLabel ?statement ?start ?end ?article ?articleEn WHERE {{
  ?statement ps:P54 wd:{team_qid} .
  ?player p:P54 ?statement .
  OPTIONAL {{ ?statement pq:P580 ?start . }}
  OPTIONAL {{ ?statement pq:P582 ?end . }}
  OPTIONAL {{ ?article schema:about ?player ; schema:isPartOf <https://{language}.wikipedia.org/> . }}
  OPTIONAL {{ ?articleEn schema:about ?player ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
""".strip()
        memberships: List[Membership] = []
        for row in self.run_query(sparql):
            player_qid = qid_from_uri(row.get("player", {}).get("value", ""))
            if not player_qid:
                continue
            wikipedia_url = row.get("article", {}).get("value") or row.get(
                "articleEn", {}
            ).get("value")
            memberships.append(
                Membership(
                    player_qid=player_qid,
                    player_label=row.get("playerLabel", {}).get("value", player_qid),
                    statement_id=row.get("statement", {}).get("value", ""),
                    start=_date_value(row.get("start")),
                    end=_date_value(row.get("end")),
                    wikipedia_url=wikipedia_url,
                )
            )
        return memberships

    # -- name search ---------------------------------------------------------
    @staticmethod
    def _people_search_query(names: List[str], team_qid: str, language: str) -> str:
        """SPARQL looking each of ``names`` up as a person's label or alias.

        Squad players without a Wikipedia article (or with one that isn't
        connected to Wikidata) can only be found by name. To keep that honest,
        the query is deliberately narrow: an **exact** label/alias match, on a
        human, who is an athlete by occupation or already has some P54
        statement. ``?atTeam`` flags a candidate that already plays for this
        very team, which settles otherwise ambiguous names.
        """
        values = " ".join(
            f'"{_escape_literal(name)}"@{lang}'
            for name in names
            for lang in _label_languages(language)
        )
        return f"""
SELECT DISTINCT ?name ?player ?playerLabel ?atTeam ?article ?articleEn WHERE {{
  VALUES ?name {{ {values} }}
  {{ ?player rdfs:label ?name . }} UNION {{ ?player skos:altLabel ?name . }}
  ?player wdt:P31 wd:Q5 .
  FILTER (
    EXISTS {{ ?player wdt:P106/wdt:P279* wd:{ATHLETE_CLASS} }}
    || EXISTS {{ ?player wdt:P54 ?anyTeam }}
  )
  BIND ( EXISTS {{ ?player wdt:P54 wd:{team_qid} }} AS ?atTeam )
  OPTIONAL {{ ?article schema:about ?player ; schema:isPartOf <https://{language}.wikipedia.org/> . }}
  OPTIONAL {{ ?articleEn schema:about ?player ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language},en". }}
}}
""".strip()

    def search_people(
        self, names: List[str], team_qid: str, language: str = "en"
    ) -> Dict[str, List[PersonMatch]]:
        """Map each searchable name to the Wikidata items carrying it.

        Names that match nothing (and names too generic to search, see
        ``_SEARCHABLE_NAME_RE``) are simply absent from the result. Picking a
        winner among several candidates is left to
        ``resolve.select_person_match`` — this only reports what exists.
        """
        unique = [
            name
            for name in dict.fromkeys(n.strip() for n in names if n and n.strip())
            if _SEARCHABLE_NAME_RE.fullmatch(name.strip())
        ]
        matches: Dict[str, List[PersonMatch]] = {}
        for batch in _chunks(unique, SEARCH_BATCH_SIZE):
            sparql = self._people_search_query(batch, team_qid, language)
            for row in self.run_query(sparql):
                qid = qid_from_uri(row.get("player", {}).get("value", ""))
                name = row.get("name", {}).get("value")
                if not qid or not name:
                    continue
                wikipedia_url = row.get("article", {}).get("value") or row.get(
                    "articleEn", {}
                ).get("value")
                found = matches.setdefault(name, [])
                if any(m.qid == qid for m in found):
                    continue  # same item matched in several languages
                found.append(
                    PersonMatch(
                        name=name,
                        qid=qid,
                        label=row.get("playerLabel", {}).get("value", qid),
                        at_team=row.get("atTeam", {}).get("value") == "true",
                        wikipedia_url=wikipedia_url,
                    )
                )
        return matches


def _chunks(items: List[str], size: int) -> Iterator[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _escape_literal(text: str) -> str:
    """Escape a name for use inside a SPARQL double-quoted literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _label_languages(language: str) -> List[str]:
    """The label languages a name is searched in, ``language`` first."""
    return list(dict.fromkeys([language, *EXTRA_LABEL_LANGUAGES]))


def _date_value(binding: Optional[dict]) -> Optional[str]:
    """Extract a short ISO date (YYYY[-MM[-DD]]) from a WDQS time binding."""
    if not binding:
        return None
    value = binding.get("value", "")
    if not value:
        return None
    # WDQS returns e.g. "2021-07-01T00:00:00Z"; keep the date part.
    return value.split("T", 1)[0].lstrip("+") or None
