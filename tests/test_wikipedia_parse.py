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


def _load_vfb() -> str:
    return (FIXTURES / "squad_sample_vfb.wikitext").read_text(encoding="utf-8")


def _load_fcb() -> str:
    return (FIXTURES / "squad_sample_fcb.wikitext").read_text(encoding="utf-8")


def _load_fck() -> str:
    return (FIXTURES / "squad_sample_fck.wikitext").read_text(encoding="utf-8")


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


def test_parses_vfb_wikilink_table():
    players = parse_squad_players(_load_vfb())
    names = [p.name for p in players]
    name_set = set(names)

    # 32 current players across the four position groups.
    assert len(players) == 32
    assert {"Fabian Bredlow", "Angelo Stiller", "Deniz Undav", "Tiago Tomás"} <= name_set

    # Comments that open *inside* a cell (e.g. "|| 2027<!-- VERLIEHEN...")
    # swallow the following rows; those loaned players must not appear, while
    # the player whose own row merely ends with the comment is still kept.
    assert "Stefan Drljača" in name_set  # row ends with the opening comment
    assert "Laurin Ulrich" in name_set  # row ends with the opening comment
    assert "Florian Hellstern" not in name_set  # inside the comment
    assert "Noah Darvich" not in name_set  # inside the comment
    assert "Yannik Keitel" not in name_set  # inside the comment

    # The coaching-staff table is excluded by its heading.
    assert "Sebastian Hoeneß" not in name_set

    # "Die Jahrhundert-Elf" is a wikitable with a "Spieler" header column, but
    # its heading is not a squad heading, so the gate keeps the historic XI out.
    assert "Timo Hildebrand" not in name_set
    assert "Jürgen Klinsmann" not in name_set

    # A player also listed under Transfers is not double-counted.
    assert names.count("Marius Funk") == 1


def test_parses_fcb_first_team_heading():
    # FC Basel puts the Spieler-column wikitable straight under "Die 1.
    # Mannschaft" with no "Kader" subsection, so the squad heading gate must
    # also recognise a first-team heading — otherwise the whole table is skipped.
    players = parse_squad_players(_load_fcb())
    names = [p.name for p in players]
    name_set = set(names)

    assert len(players) == 30
    assert "Jonas Omlin" in name_set  # first row, {{0}}-padded number
    assert "Djordje Jovanovic" in name_set  # last row

    # The commented-out row must not be parsed.
    assert "Juan Carlos Gauto" not in name_set

    # "Letzter Verein" holds clubs, not players.
    assert "Borussia Mönchengladbach" not in name_set
    assert "eigene Jugend" not in name_set

    # The "Verwaltungsrat, Vorstand und Betreuerstab" table is excluded by its
    # heading — no board members or coaches leak in.
    assert "David Degen" not in name_set
    assert "Stephan Lichtsteiner" not in name_set
    assert "Valentin Stocker" not in name_set


def test_fcb_link_targets_and_numbers():
    players = {p.name: p for p in parse_squad_players(_load_fcb())}

    # {{0}} padding is stripped from the number; plain link title == name.
    assert players["Jonas Omlin"].number == "1"
    assert players["Jonas Omlin"].title == "Jonas Omlin"
    assert players["Jonas Omlin"].section == "Die 1. Mannschaft"

    # Disambiguated, piped wikilinks keep their full target.
    assert players["Nicolas Vouilloz"].title == "Nicolas Vouilloz (Fussballspieler)"
    assert players["Ibrahim Salah"].title == "Ibrahim Salah (Fußballspieler, 2001)"
    assert players["Ibrahim Salah"].number == "21"


def test_parses_fck_spieler_subsection():
    # 1. FC Köln nests the table one level deeper: the "Kader" heading is on the
    # parent ("== Aktueller Kader 2026/27 =="), the table under a bare
    # "=== Spieler ===". Read flat, that subsection is judged on its own heading,
    # so the gate must accept a whole-heading "Spieler".
    players = parse_squad_players(_load_fck())
    names = [p.name for p in players]
    name_set = set(names)

    assert len(players) == 26
    assert "Marvin Schwäbe" in name_set  # first row, {{Kapitän}} suffix, {{0}} nr
    assert "Matthias Köbbing" in name_set  # plain-text player (no article link)
    assert "Fynn Schenten" in name_set  # last row, {{FN|II}} footnote suffix

    # Commented-out rows must not be parsed.
    assert "Cenny Neumann" not in name_set
    assert "Emin Kujović" not in name_set
    assert "Jaka Čuber Potočnik" not in name_set

    # The Transfers table's heading is excluded ("transfer").
    assert "Rasmus Carstensen" not in name_set
    assert "Eric Martel" not in name_set

    # The Trainerstab table's heading is excluded ("trainer").
    assert "René Wagner" not in name_set

    # "Sportliche Leitung" is not a squad heading, so its "Name"-column
    # management table (Geschäftsführer, Direktoren) must not be read.
    assert "Thomas Kessler" not in name_set
    assert "Lukas Berg" not in name_set
    assert "Tim Steidten" not in name_set


def test_fck_link_targets_and_numbers():
    players = {p.name: p for p in parse_squad_players(_load_fck())}

    # {{0}} padding stripped; trailing {{Kapitän}} does not corrupt the link.
    assert players["Marvin Schwäbe"].title == "Marvin Schwäbe"
    assert players["Marvin Schwäbe"].number == "1"
    assert players["Marvin Schwäbe"].section == "Spieler"

    # Plain-text player: no article link, so no title.
    assert players["Matthias Köbbing"].title is None
    assert players["Matthias Köbbing"].number == "44"

    # Empty "Nr." cell yields no number, but the player is still parsed.
    assert players["Elias Bakatukanda"].number is None


def test_vfb_link_targets():
    players = {p.name: p for p in parse_squad_players(_load_vfb())}

    # Empty "Nr." cell yields no number, but the player is still parsed.
    assert players["Laurin Ulrich"].number is None
    # Disambiguated links keep their full target.
    assert players["Chema"].title == "Chema (Fußballspieler)"
    assert players["Lazar Jovanović"].title == "Lazar Jovanović (Fußballspieler, 2006)"
    # Trailing {{Kapitän}} does not corrupt the linked name/number.
    assert players["Atakan Karazor"].title == "Atakan Karazor"
    assert players["Atakan Karazor"].number == "16"
