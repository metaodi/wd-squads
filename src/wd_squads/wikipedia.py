"""Read football squads from Wikipedia and resolve players to Wikidata items."""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

import mwparserfromhell

from .http_client import HttpClient
from .models import CareerSpell, SquadPlayer, Team

log = logging.getLogger(__name__)

# Template names (normalised) that describe one squad player.
#
# English (and other {{fs player}}-style) editions wrap each player in an
# ``{{fs player}}`` template. German Wikipedia instead renders the squad as a
# ``{| class="wikitable"`` table whose player cells use ``{{PersonZelle}}``.
# We recognise both so a single parser works across editions (auto-detect).
FS_PLAYER_TEMPLATES = {"fs player", "football squad player"}
PERSON_ZELLE_TEMPLATE = "personzelle"

# Swiss/German ice hockey squads (e.g. National League clubs) are not listed
# inline in the club article at all: the article just transcludes a
# per-club navbox template (see SQUAD_NAVBOX_RE below) with Format=Tabelle,
# and that template's own wikitext holds one ``{{Eishockeykader/Spieler}}``
# call per player. It needs no heading gate: unlike {{PersonZelle}}, this
# template name is unambiguous, and the coaching staff uses a distinct
# ``Eishockeykader/Trainer`` template that we simply never match.
EISHOCKEYKADER_SPIELER_TEMPLATE = "eishockeykader/spieler"

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

# A club article whose squad is transcluded rather than inline (see above)
# names the transclusion "Navigationsleiste Kader ..." by convention (e.g.
# "Navigationsleiste Kader der ZSC Lions"). Matched loosely (no fixed
# connecting word) since it may read "... der X", "... des X" etc.
SQUAD_NAVBOX_RE = re.compile(r"^navigationsleiste kader\b", re.IGNORECASE)


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


def _player_from_eishockeykader_spieler(template, heading: Optional[str]) -> Optional[SquadPlayer]:
    """Build a player from an ``{{Eishockeykader/Spieler}}`` call.

    Used by Swiss/German ice hockey clubs. ``Vorname``/``Nachname`` give the
    display name; an explicit ``Link`` (full, possibly disambiguated article
    title) overrides the default of linking to "Vorname Nachname", the same
    role ``l=`` plays for ``{{PersonZelle}}``.
    """
    given = _param(template, "Vorname") or ""
    family = _param(template, "Nachname") or ""
    display = " ".join(part for part in (given, family) if part).strip()
    if not display:
        return None
    title = _param(template, "Link") or display
    return SquadPlayer(
        name=display,
        title=title,
        number=_param(template, "Nummer"),
        position=_param(template, "Position"),
        section=heading,
    )


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
            # A dash placeholder ("-"/"–"/"—") means "no number assigned"
            # (e.g. Servette's academy call-ups); treat it like an empty cell.
            if number and set(number) <= {"-", "–", "—"}:
                number = None
        players.append(
            SquadPlayer(name=display, title=title, number=number, section=heading)
        )
    return players


def parse_squad_players(wikitext: str) -> List[SquadPlayer]:
    """Extract the current-squad players from an article's wikitext.

    Auto-detects the squad format per section: English-style ``{{fs player}}``
    templates, German-style ``{{PersonZelle}}`` table cells, plain
    ``{| class="wikitable"`` tables that link each player as a bare
    ``[[wikilink]]`` in a "Spieler"/"Name" column (FC Zürich, Schalke 04), and
    ``{{Eishockeykader/Spieler}}`` calls (Swiss/German ice hockey) are all
    recognised, so the same parser serves editions/sports that use any of
    them. Note that for the ice hockey format, ``wikitext`` is typically the
    *transcluded squad template's* wikitext, not the club article's own (see
    ``find_squad_template_title``).

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
            elif name == EISHOCKEYKADER_SPIELER_TEMPLATE:
                _add(_player_from_eishockeykader_spieler(template, heading))

        # Plain-wikilink squad tables (FC Zürich, Schalke 04): no player
        # template, players are [[wikilinks]] in a "Spieler"/"Name" column.
        if is_squad_section:
            for table in section.filter_tags(matches=lambda t: t.tag == "table"):
                for player in _players_from_wikitable(table, heading):
                    _add(player)
    return players


def find_squad_template_title(wikitext: str) -> Optional[str]:
    """Return the title of a transcluded ``Navigationsleiste Kader ...``
    squad template, or ``None`` if the article doesn't transclude one.

    Some clubs (Swiss/German ice hockey) don't list their squad inline at
    all; the article just transcludes a per-club navbox template, and the
    actual roster lives in that template's own wikitext (fetch it as
    ``f"Vorlage:{title}"`` and feed it to ``parse_squad_players`` instead).
    Pure function, no network.
    """
    code = mwparserfromhell.parse(wikitext or "")
    for template in code.filter_templates():
        title = str(template.name).strip()
        if SQUAD_NAVBOX_RE.match(_normalise_template_name(title)):
            return title
    return None


# --- Player career history (start/end years per club) -----------------------
#
# A player's own Wikipedia article often carries an infobox with a per-club
# career history that can suggest P54 start/end years. Three formats are
# recognised (auto-detected, like the squad formats above): the English
# ``{{Infobox football biography}}``, whose ``yearsN``/``clubsN`` positional
# pairs list one club per index; the German ``{{Infobox Fußballspieler}}``,
# whose ``vereine_tabelle`` parameter holds one ``{{Team-Station}}`` call per
# club; and the German ``{{Infobox Eishockeyspieler}}``, whose ``JahreN``/
# ``VereinN`` pairs mirror the English football biography's numbered-field
# shape. Other infoboxes (e.g. the *English* ``{{Infobox ice hockey player}}``,
# which only gives an overall ``career_start``/``career_end`` and a
# ``played_for`` list with no years per club) cannot be attributed to a
# specific club and are skipped rather than guessed at.

_DASH_RE = re.compile(r"[\-‐‑‒–—−]")
_YEAR_RE = re.compile(r"(\d{4})")
_LOAN_MARKER_RE = re.compile(r"\(\s*loan\s*\)", re.IGNORECASE)
# The German ice hockey infobox spells open-ended spans out in words instead
# of a trailing/leading dash: "seit 2019" (since) and "bis 1997" (until).
_SEIT_RE = re.compile(r"\bseit\b", re.IGNORECASE)
_BIS_RE = re.compile(r"\bbis\b", re.IGNORECASE)


def _first_year(text: str) -> Optional[int]:
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def _parse_years_range(raw: str) -> tuple:
    """Parse an infobox ``years`` value into ``(start, end, ongoing)``.

    ``"1994–1999"`` -> ``(1994, 1999, False)``; ``"1994"`` (no dash, a single
    season) -> ``(1994, 1994, False)``; ``"2020–"`` (open-ended, still
    active) -> ``(2020, None, True)``; ``"seit 2019"`` ("since", the German
    ice hockey infobox's open-ended form) -> ``(2019, None, True)``; ``"bis
    1997"`` ("until", an unknown start year) -> ``(None, 1997, False)``.
    """
    raw = (raw or "").strip()
    if not raw:
        return None, None, False
    if _SEIT_RE.search(raw):
        year = _first_year(raw)
        return year, None, year is not None
    if _BIS_RE.search(raw):
        return None, _first_year(raw), False
    parts = _DASH_RE.split(raw, maxsplit=1)
    if len(parts) == 1:
        year = _first_year(parts[0])
        return year, year, False
    start = _first_year(parts[0])
    end = _first_year(parts[1])
    ongoing = start is not None and end is None
    return start, end, ongoing


def _parse_club_value(value) -> tuple:
    """Return ``(article_title, display_name, is_loan)`` for a club value.

    Handles a bare wikilink, a piped wikilink, plain text, a leading ``→``
    (the English convention for a loan move), and a trailing ``(loan)``.
    """
    text = str(value)
    loan = "→" in text or bool(_LOAN_MARKER_RE.search(text))
    text = text.replace("→", "")
    code = mwparserfromhell.parse(text)
    links = code.filter_wikilinks()
    if links:
        link = links[0]
        title: Optional[str] = str(link.title).strip()
        display = str(link.text).strip() if link.text else title
    else:
        title = None
        display = code.strip_code().strip()
    display = _LOAN_MARKER_RE.sub("", display).strip()
    return title or None, display, loan


def _spells_from_numbered_fields(template, years_key: str, club_key: str) -> List[CareerSpell]:
    """Read ``{years_key}1``/``{club_key}1``, ``{years_key}2``/``{club_key}2``,
    ... pairs — the shape shared by the English football biography infobox
    (``years``/``clubs``) and the German ice hockey infobox (``Jahre``/
    ``Verein``).
    """
    spells: List[CareerSpell] = []
    n = 1
    while n <= 40 and (template.has(f"{years_key}{n}") or template.has(f"{club_key}{n}")):
        if template.has(f"{club_key}{n}"):
            years_raw = _param(template, f"{years_key}{n}") or ""
            title, display, loan = _parse_club_value(template.get(f"{club_key}{n}").value)
            if display:
                start, end, ongoing = _parse_years_range(years_raw)
                spells.append(
                    CareerSpell(
                        club_name=display,
                        club_title=title,
                        start_year=start,
                        end_year=end,
                        ongoing=ongoing,
                        loan=loan,
                    )
                )
        n += 1
    return spells


def _spells_from_football_biography(template) -> List[CareerSpell]:
    return _spells_from_numbered_fields(template, "years", "clubs")


def _spells_from_eishockeyspieler(template) -> List[CareerSpell]:
    return _spells_from_numbered_fields(template, "Jahre", "Verein")


def _spells_from_fussballspieler(template) -> List[CareerSpell]:
    if not template.has("vereine_tabelle"):
        return []
    spells: List[CareerSpell] = []
    for sub in template.get("vereine_tabelle").value.filter_templates():
        if _normalise_template_name(str(sub.name)) != "team-station":
            continue
        values = [p.value for p in sub.params if not p.showkey]
        if len(values) < 2:
            continue
        years_raw = values[0].strip_code().strip()
        title, display, _loan = _parse_club_value(values[1])
        if not display:
            continue
        start, end, ongoing = _parse_years_range(years_raw)
        spells.append(
            CareerSpell(
                club_name=display,
                club_title=title,
                start_year=start,
                end_year=end,
                ongoing=ongoing,
                loan=bool(_param(sub, "leihe")),
            )
        )
    return spells


# Normalised infobox template name -> parser. Checked in this order; the
# first infobox template found in the article wins (a player has exactly one).
_CAREER_INFOBOX_PARSERS = {
    "infobox football biography": _spells_from_football_biography,
    "infobox footballer": _spells_from_football_biography,
    "infobox fußballspieler": _spells_from_fussballspieler,
    "infobox eishockeyspieler": _spells_from_eishockeyspieler,
}


def parse_career_spells(wikitext: str) -> List[CareerSpell]:
    """Extract senior-club career spells from a player's own infobox.

    Returns ``[]`` when the article has no infobox, or an infobox in a
    format with no per-club years (e.g. ice hockey's ``played_for`` list).
    Pure function, no network; see ``_CAREER_INFOBOX_PARSERS`` for the
    recognised formats.
    """
    code = mwparserfromhell.parse(wikitext or "")
    for template in code.filter_templates():
        parser = _CAREER_INFOBOX_PARSERS.get(_normalise_template_name(str(template.name)))
        if parser:
            return parser(template)
    return []


def _redirect_map(query: dict) -> Dict[str, str]:
    rename: Dict[str, str] = {}
    for entry in query.get("normalized", []):
        rename[entry["from"]] = entry["to"]
    for entry in query.get("redirects", []):
        rename[entry["from"]] = entry["to"]
    return rename


def _follow_redirects(rename: Dict[str, str], title: str) -> str:
    resolved = title
    for _ in range(5):
        if resolved in rename:
            resolved = rename[resolved]
        else:
            break
    return resolved


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
        rename = _redirect_map(query)

        final_qid: Dict[str, Optional[str]] = {}
        for page in query.get("pages", []):
            qid = page.get("pageprops", {}).get("wikibase_item")
            final_qid[page.get("title")] = qid

        return {
            title: final_qid.get(_follow_redirects(rename, title)) for title in titles
        }

    def fetch_wikitext_batch(
        self, titles: List[str], language: Optional[str] = None
    ) -> Dict[str, str]:
        """Map each of ``titles`` to its current wikitext, in one request.

        Unlike ``fetch_wikitext`` (one page via the ``parse`` action, used for
        club squads), this batches up to ~50 titles through ``action=query``
        so per-player infobox lookups (``get_career_spells``) don't cost one
        request each. Titles with no page (or no content) map to ``""``.
        """
        data = self.http.get_json(
            self._api_url(language),
            params={
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(titles),
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            },
        )
        query = data.get("query", {})
        rename = _redirect_map(query)

        content_by_title: Dict[str, str] = {}
        for page in query.get("pages", []):
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            content = revisions[0].get("slots", {}).get("main", {}).get("content")
            if content:
                content_by_title[page.get("title")] = content

        return {
            title: content_by_title.get(_follow_redirects(rename, title), "")
            for title in titles
        }

    def get_career_spells(
        self, titles: List[str], language: Optional[str] = None
    ) -> Dict[str, List[CareerSpell]]:
        """Fetch and parse the career history from each player's own article.

        Only meant to be called for players a suggestion is already being
        made about (see ``diff.suggestion_titles``) — fetching every squad
        member's full biography just to enrich the few that need it would be
        wasteful.
        """
        result: Dict[str, List[CareerSpell]] = {}
        unique = list(dict.fromkeys(t for t in titles if t))
        for batch in _chunks(unique, 20):
            wikitexts = self.fetch_wikitext_batch(batch, language)
            for title, wikitext in wikitexts.items():
                result[title] = parse_career_spells(wikitext)
        return result

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
        squad_template = find_squad_template_title(wikitext)
        if squad_template:
            wikitext = self.fetch_wikitext(f"Vorlage:{squad_template}", team.language) or ""
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
