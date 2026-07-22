from pathlib import Path

from conftest import FIXTURES

from wd_squads.wikipedia import parse_squad_players


def _load() -> str:
    return (FIXTURES / "squad_sample.wikitext").read_text(encoding="utf-8")


def _load_de() -> str:
    return (FIXTURES / "squad_sample_de.wikitext").read_text(encoding="utf-8")


def _load_fcz() -> str:
    return (FIXTURES / "squad_sample_fcz.wikitext").read_text(encoding="utf-8")


def _load_schalke() -> str:
    return (FIXTURES / "squad_sample_schalke.wikitext").read_text(encoding="utf-8")


def test_parses_expected_players():
    players = parse_squad_players(_load())
    names = {p.name for p in players}
    # Four current players; the "Notable former players" one is excluded.
    assert names == {"Alice Keeper", "Bob", "Charlie Noitem", "Dave Loanee"}
    assert "Old Timer" not in names


def test_extracts_titles_numbers_positions():
    players = {p.name: p for p in parse_squad_players(_load())}

    alice = players["Alice Keeper"]
    assert alice.title == "Alice Keeper"
    assert alice.number == "1"
    assert alice.position == "GK"
    assert alice.section == "Current squad"

    # Piped wikilink: display text differs from the article title.
    bob = players["Bob"]
    assert bob.title == "Bob Striker"
    assert bob.name == "Bob"

    # Plain text name (no wikilink) has no article title.
    assert players["Charlie Noitem"].title is None

    # {{football squad player}} alias and a subsection heading both work.
    assert players["Dave Loanee"].section == "Out on loan"


def test_handles_empty_input():
    assert parse_squad_players("") == []


# --- German Wikipedia ({{PersonZelle}} table) format ------------------------


def test_parses_german_squad_table():
    players = parse_squad_players(_load_de())
    names = {p.name for p in players}
    # The six current-squad players from the "Aktueller Kader" table.
    assert names == {
        "Gregor Kobel",
        "Alexander Meyer",
        "Nico Schlotterbeck",
        "Daniel Svensson",
        "Emre Can",
        "Mussa Kaba",
    }
    # Coaching staff, transfers and former players must NOT be counted.
    assert "Niko Kovač" not in names  # Trainer- und Betreuerstab
    assert "Jobe Bellingham" not in names  # Kaderveränderungen / Zugänge
    assert "Marco Reus" not in names  # Bekannte ehemalige Spieler
    # Commented-out rows (loaned out / second team) are ignored.
    assert "Ayman Azhil" not in names
    assert "Julien Duranville" not in names


def test_german_link_targets():
    players = {p.name: p for p in parse_squad_players(_load_de())}

    # Plain name links to the article of the same title.
    assert players["Gregor Kobel"].title == "Gregor Kobel"
    assert players["Gregor Kobel"].section == "Aktueller Kader"

    # k= adds a parenthetical disambiguator to the link target.
    assert players["Alexander Meyer"].title == "Alexander Meyer (Fußballspieler, 1991)"
    assert players["Daniel Svensson"].title == "Daniel Svensson (Fußballspieler)"

    # nl=1 marks a player with no article, so there is no link title.
    assert players["Mussa Kaba"].title is None


# --- German/Swiss wikilink-table format (FC Zürich, Schalke 04) --------------
#
# Some squads are plain ``{| class="wikitable"`` tables that link each player as
# a bare ``[[wikilink]]`` in a "Spieler"/"Name" column rather than using
# {{PersonZelle}}. The player column is found by its header; other columns
# (previous club) also hold links and must be ignored.


def test_parses_fcz_wikilink_table():
    players = parse_squad_players(_load_fcz())
    names = {p.name for p in players}
    # Every player from the "Kader der Saison 2026/27" table (header "Spieler").
    assert names == {
        "Silas Huber",
        "Jewgen Morozow",
        "Heinz Lindner",
        "Lindrit Kamberi",
        "Livano Comenencia",
        "Chris Kablan",
        "Ilan Sauter",
        "Bledian Krasniqi",
        "Jill Stiel",
        "Juan José Perea",
    }
    # Links in the "Letzter Verein" column are clubs, not players.
    assert "FC Winterthur" not in names
    assert "BSC Young Boys" not in names
    # The Betreuerstab/Vorstand table's coach must not be counted.
    assert "Marcel Koller" not in names


def test_fcz_link_targets_numbers_and_section():
    players = {p.name: p for p in parse_squad_players(_load_fcz())}

    # Plain wikilink: title equals the display name; number comes from "Nr.".
    assert players["Silas Huber"].title == "Silas Huber"
    assert players["Silas Huber"].number == "1"
    assert players["Silas Huber"].section == "Kader der Saison 2026/27"

    # Piped, disambiguated wikilink: title differs from the display name.
    assert players["Heinz Lindner"].title == "Heinz Lindner (Fußballspieler)"
    assert players["Heinz Lindner"].number == "13"


def test_parses_schalke_wikilink_table():
    players = parse_squad_players(_load_schalke())
    names = {p.name for p in players}
    # Header "Name" sits directly under {| (no leading |-); position separators
    # are colspan cells; plain-text players have no article link.
    assert names == {
        "Loris Karius",
        "Kevin Müller",
        "Johannes Siebeking",
        "Dylan Leonard",
        "Timo Becker",
        "Vitalie Becker",
        "Kenan Karaman",
        "Mika Wallentowitz",
        "Luca Vozar",
    }
    # Commented-out rows (loaned out / second team) are ignored.
    assert "Luca Podlech" not in names
    assert "Steve Noode" not in names
    assert "Ibrahima Cissé" not in names
    # Transfers and coaching-staff sections are excluded by their headings.
    assert "Junior Adamu" not in names
    assert "Miron Muslić" not in names
    # The previous-club column ("letzte Station") links clubs, not players.
    assert "Newcastle United" not in names
    assert "Holstein Kiel" not in names


def test_schalke_plaintext_captain_and_footnote():
    players = {p.name: p for p in parse_squad_players(_load_schalke())}

    # No-article players are kept with a name but no link title.
    assert players["Johannes Siebeking"].title is None
    assert players["Luca Vozar"].title is None

    # A trailing {{Kapitän}}/{{FN}} template does not corrupt the linked name.
    assert players["Kenan Karaman"].title == "Kenan Karaman"
    assert players["Kenan Karaman"].number == "19"
    assert players["Mika Wallentowitz"].title == "Mika Wallentowitz"

    # Disambiguated link target is preserved.
    assert players["Timo Becker"].title == "Timo Becker (Fußballspieler, 1997)"
