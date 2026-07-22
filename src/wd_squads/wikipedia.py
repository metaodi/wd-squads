"""Read football squads from Wikipedia and resolve players to Wikidata items."""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

import mwparserfromhell

from .http_client import HttpClient
from .models import SquadPlayer, Team

log = logging.getLogger(__name__)

# Template names (normalised) that describe one squad player.
#
# English (and other {{fs player}}-style) editions wrap each player in an
# ``{{fs player}}`` template. German Wikipedia instead renders the squad as a
# ``{| class="wikitable"`` table whose player cells use ``{{PersonZelle}}``.
# We recognise both so a single parser works across editions (auto-detect).
FS_PLAYER_TEMPLATES = {"fs player", "football squad player"}
PERSON_ZELLE_TEMPLATE = "personzelle"

# Section headings that list *former* players (or staff / transfers) even though
# they use the same squad templates. Players found under these are ignored, so
# we do not wrongly treat them as current members. The English terms are
# word-anchored; the German stems are matched as substrings because German
# forms compounds (e.g. "Kaderveränderungen", "Trainer- und Betreuerstab").
EXCLUDE_HEADING_RE = re.compile(
    r"\b(former|retired number|notable|hall of fame|no longer)\b"
    r"|ehemalig|berühmt|zugäng|abgäng|transfer|wechsel|veränderung"
    r"|trainer|betreuer|funktionstea?m|vorstand|präsidium|vereinsführung"
    r"|aufsichtsrat|geschäftsführung|verwaltung",
    re.IGNORECASE,
)

# Positive marker that a section actually holds a squad. This gate is applied
# to the German formats (the {{PersonZelle}} cells *and* the plain-wikilink
# wikitable, see below), which also appear in unrelated tables (coaching staff,
# record appearances, …); requiring a squad heading keeps those out. The
# {{fs player}} format keeps its original, ungated behaviour.
#
# Besides "Kader"/"Aufgebot", some clubs put the table straight under a
# first-team heading with no "Kader" subsection (e.g. FC Basel's "Die 1.
# Mannschaft"). We accept "Mannschaft" only when marked as the *first* team
# ("1." or "Erste") so reserve/youth/women sides ("2. Mannschaft",
# "U-19-Mannschaft", "Frauenmannschaft") — which are separate Wikidata teams —
# do not leak into the squad.
#
# Others nest the table one level deeper under a bare "Spieler" subsection whose
# parent carries the "Kader" heading (e.g. 1. FC Köln: "== Aktueller Kader ==" →
# "=== Spieler ==="). Because sections are read flat, that subsection is judged
# on its own heading, so we accept a *whole-heading* "Spieler"/"Spielerinnen".
# It is anchored (not a substring) on purpose: a bare "Spieler" heading is the
# squad, but "Bekannte Spieler" (notable players) or a "Name"-column management
# table under "Sportliche Leitung" must stay out.
SQUAD_HEADING_RE = re.compile(
    r"kader|aufgebot|(?:\b1\.|\berste)\s*mannschaft|^spieler(?:innen)?$",
    re.IGNORECASE,
)

# Some German/Swiss squads are plain ``{| class="wikitable"`` tables that link
# each player as a bare ``[[wikilink]]`` in a dedicated column instead of using
# ``{{PersonZelle}}`` (e.g. FC Zürich, Schalke 04). To read those we locate the
# player column by its header text and take only that column's link — other
# columns ("Letzter Verein"/"letzte Station") link *clubs*, which must not be
# mistaken for players. Header labels are matched lower-cased and stripped.
TABLE_NAME_HEADERS = {"spieler", "spielerin", "spielername", "name"}
TABLE_NUMBER_HEADERS = {"nr.", "nr", "no.", "no", "nummer", "rückennummer", "rn", "#"}


def _normalise_template_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def _parse_name_param(value) -> tuple[Optional[str], str]:
    """Return ``(article_title, display_name)`` for a template ``name=`` value.

    The value is usually a wikilink (``[[Lionel Messi]]`` or
    ``[[Lionel Messi|Messi]]``) but can be plain text.
    """
    code = mwparserfromhell.parse(str(value))
    links = code.filter_wikilinks()
    if links:
        link = links[0]
        title = str(link.title).strip()
        display = str(link.text).strip() if link.text else title
        return title, display
    text = code.strip_code().strip()
    return None, text


def _param(template, name: str) -> Optional[str]:
    if not template.has(name):
        return None
    value = template.get(name).value.strip_code().strip()
    return value or None


def _positional_args(template) -> List[str]:
    """Return the unnamed (positional) parameter values of a template."""
    return [p.value.strip_code().strip() for p in template.params if not p.showkey]


def _player_from_fs_template(template, heading: Optional[str]) -> Optional[SquadPlayer]:
    """Build a player from an English-style ``{{fs player}}`` template."""
    if not template.has("name"):
        return None
    title, display = _parse_name_param(template.get("name").value)
    if not display:
        return None
    return SquadPlayer(
        name=display,
        title=title,
        number=_param(template, "no"),
        position=_param(template, "pos"),
        section=heading,
    )


def _player_from_person_zelle(template, heading: Optional[str]) -> Optional[SquadPlayer]:
    """Build a player from a German-style ``{{PersonZelle}}`` table cell.

    ``{{PersonZelle|Vorname|Nachname}}`` renders (and links) "Vorname Nachname".
    Named parameters refine the link target:

    * ``nl=1``  – the player has no article, so there is no link (``title`` None);
    * ``l=…``   – an explicit article title (Lemma) that differs from the name;
    * ``k=…``   – a disambiguator appended in parentheses, e.g.
      ``{{PersonZelle|Alexander|Meyer|k=Fußballspieler, 1991}}`` links to
      "Alexander Meyer (Fußballspieler, 1991)".
    """
    args = _positional_args(template)
    given = args[0] if len(args) >= 1 else ""
    family = args[1] if len(args) >= 2 else ""
    display = " ".join(part for part in (given, family) if part).strip()
    if not display:
        return None

    if _param(template, "nl"):
        title: Optional[str] = None
    elif _param(template, "l"):
        title = _param(template, "l")
    elif _param(template, "k"):
        title = f"{display} ({_param(template, 'k')})"
    else:
        title = display

    return SquadPlayer(name=display, title=title, section=heading)


def _table_rows(table) -> List[list]:
    """Return the table's rows as lists of cell tags.

    Cells directly under the table (header cells written before the first
    ``|-``, as Schalke does) form an implicit leading row; every ``|-`` row
    (as FC Zürich writes its header) follows. This normalises both so the
    header can be found the same way regardless of style.
    """
    rows: List[list] = []
    lead = [n for n in table.contents.nodes if getattr(n, "tag", None) in ("td", "th")]
    if lead:
        rows.append(lead)
    for node in table.contents.nodes:
        if getattr(node, "tag", None) == "tr":
            rows.append(
                node.contents.filter_tags(matches=lambda t: t.tag in ("td", "th"))
            )
    return rows


def _cell_has_player_template(cell) -> bool:
    """True if the cell renders a player via {{PersonZelle}}/{{fs player}}."""
    for template in cell.contents.filter_templates():
        name = _normalise_template_name(str(template.name))
        if name in FS_PLAYER_TEMPLATES or name == PERSON_ZELLE_TEMPLATE:
            return True
    return False


def _players_from_wikitable(table, heading: Optional[str]) -> List[SquadPlayer]:
    """Read players from a plain wikitable that links each in a "Spieler"/"Name"
    column (bare ``[[wikilink]]`` or plain text), e.g. FC Zürich / Schalke 04.

    The player column is found by its header label; only that column is read, so
    club links in "Letzter Verein"/"letzte Station" are ignored. Position-group
    separator rows (a single ``colspan`` cell) have too few columns and are
    skipped. Commented-out rows never reach here — the parser drops them.
    """
    rows = _table_rows(table)

    name_col: Optional[int] = None
    number_col: Optional[int] = None
    header_index: Optional[int] = None
    for index, cells in enumerate(rows):
        labels = [c.contents.strip_code().strip().lower() for c in cells]
        candidate = next(
            (i for i, label in enumerate(labels) if label in TABLE_NAME_HEADERS), None
        )
        if candidate is not None:
            name_col = candidate
            number_col = next(
                (i for i, label in enumerate(labels) if label in TABLE_NUMBER_HEADERS),
                None,
            )
            header_index = index
            break
    if name_col is None or header_index is None:
        return []

    players: List[SquadPlayer] = []
    for cells in rows[header_index + 1 :]:
        if len(cells) <= name_col:
            continue  # position-group separator / short row
        name_cell = cells[name_col]
        # A cell rendered with {{PersonZelle}}/{{fs player}} is handled by the
        # template pass; don't also read it here (and don't mistake leftover
        # cell-attribute text for a name).
        if _cell_has_player_template(name_cell):
            continue
        title, display = _parse_name_param(name_cell.contents)
        if not display:
            continue
        number = None
        if number_col is not None and len(cells) > number_col:
            number = cells[number_col].contents.strip_code().strip() or None
        players.append(
            SquadPlayer(name=display, title=title, number=number, section=heading)
        )
    return players


def parse_squad_players(wikitext: str) -> List[SquadPlayer]:
    """Extract the current-squad players from an article's wikitext.

    Auto-detects the squad format per section: English-style ``{{fs player}}``
    templates, German-style ``{{PersonZelle}}`` table cells, and plain
    ``{| class="wikitable"`` tables that link each player as a bare
    ``[[wikilink]]`` in a "Spieler"/"Name" column (FC Zürich, Schalke 04) are
    all recognised, so the same parser serves editions that use any of them.

    This is a pure function (no network) and is the heart of the tool, so it is
    covered directly by unit tests.
    """
    code = mwparserfromhell.parse(wikitext or "")
    players: List[SquadPlayer] = []
    seen: set[str] = set()

    for section in code.get_sections(flat=True, include_headings=True):
        headings = section.filter_headings()
        heading = headings[0].title.strip_code().strip() if headings else None
        if heading and EXCLUDE_HEADING_RE.search(heading):
            continue
        # The German formats ({{PersonZelle}} cells and plain-wikilink tables)
        # also appear in non-squad tables (staff, records), so only trust them
        # under an explicit "Kader"/"Aufgebot" heading.
        is_squad_section = bool(heading and SQUAD_HEADING_RE.search(heading))

        def _add(player: Optional[SquadPlayer]) -> None:
            if player is None:
                return
            key = player.title or player.name
            if not key or key in seen:
                return
            seen.add(key)
            players.append(player)

        for template in section.filter_templates():
            name = _normalise_template_name(str(template.name))
            if name in FS_PLAYER_TEMPLATES:
                _add(_player_from_fs_template(template, heading))
            elif name == PERSON_ZELLE_TEMPLATE and is_squad_section:
                _add(_player_from_person_zelle(template, heading))

        # Plain-wikilink squad tables (FC Zürich, Schalke 04): no player
        # template, players are [[wikilinks]] in a "Spieler"/"Name" column.
        if is_squad_section:
            for table in section.filter_tags(matches=lambda t: t.tag == "table"):
                for player in _players_from_wikitable(table, heading):
                    _add(player)
    return players


class WikipediaClient:
    def __init__(self, http: HttpClient, language: str = "en") -> None:
        self.http = http
        self.default_language = language

    def _api_url(self, language: Optional[str]) -> str:
        return f"https://{language or self.default_language}.wikipedia.org/w/api.php"

    def fetch_wikitext(self, title: str, language: Optional[str] = None) -> Optional[str]:
        data = self.http.get_json(
            self._api_url(language),
            params={
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            },
        )
        if "error" in data:
            log.warning("Could not fetch wikitext for %r: %s", title, data["error"])
            return None
        return data.get("parse", {}).get("wikitext")

    def resolve_qids(
        self, titles: List[str], language: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        """Map each Wikipedia article title to its Wikidata Q-ID (or None)."""
        result: Dict[str, Optional[str]] = {}
        unique = list(dict.fromkeys(t for t in titles if t))
        for batch in _chunks(unique, 50):
            result.update(self._resolve_batch(batch, language))
        return result

    def _resolve_batch(
        self, titles: List[str], language: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        data = self.http.get_json(
            self._api_url(language),
            params={
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "titles": "|".join(titles),
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            },
        )
        query = data.get("query", {})
        # Follow title normalisation and redirects to the final page title.
        rename: Dict[str, str] = {}
        for entry in query.get("normalized", []):
            rename[entry["from"]] = entry["to"]
        for entry in query.get("redirects", []):
            rename[entry["from"]] = entry["to"]

        final_qid: Dict[str, Optional[str]] = {}
        for page in query.get("pages", []):
            qid = page.get("pageprops", {}).get("wikibase_item")
            final_qid[page.get("title")] = qid

        out: Dict[str, Optional[str]] = {}
        for title in titles:
            resolved = title
            # A title may be normalised, then redirected; follow the chain.
            for _ in range(5):
                if resolved in rename:
                    resolved = rename[resolved]
                else:
                    break
            out[title] = final_qid.get(resolved)
        return out

    def get_squad(self, team: Team) -> List[SquadPlayer]:
        """Return the current squad for ``team`` with Wikidata Q-IDs resolved."""
        if not team.wikipedia_title:
            log.info(
                "Team %s (%s) has no %s.wikipedia article",
                team.qid,
                team.label,
                team.language,
            )
            return []
        wikitext = self.fetch_wikitext(team.wikipedia_title, team.language)
        if not wikitext:
            return []
        players = parse_squad_players(wikitext)
        mapping = self.resolve_qids(
            [p.title for p in players if p.title], team.language
        )
        for player in players:
            if player.title:
                player.qid = mapping.get(player.title)
        return players


def _chunks(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
