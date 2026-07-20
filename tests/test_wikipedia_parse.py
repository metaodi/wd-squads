from pathlib import Path

from conftest import FIXTURES

from wd_squads.wikipedia import parse_squad_players


def _load() -> str:
    return (FIXTURES / "squad_sample.wikitext").read_text(encoding="utf-8")


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
