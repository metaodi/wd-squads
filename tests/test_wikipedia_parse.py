from pathlib import Path

from conftest import FIXTURES

from wd_squads.wikipedia import parse_squad_players


def _load() -> str:
    return (FIXTURES / "squad_sample.wikitext").read_text(encoding="utf-8")


def _load_de() -> str:
    return (FIXTURES / "squad_sample_de.wikitext").read_text(encoding="utf-8")


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
