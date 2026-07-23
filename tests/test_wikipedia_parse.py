from pathlib import Path

from conftest import FIXTURES

from wd_squads.wikipedia import (
    find_squad_template_title,
    parse_career_spells,
    parse_squad_players,
)


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


def _load_servette() -> str:
    return (FIXTURES / "squad_sample_servette.wikitext").read_text(encoding="utf-8")


def _load_hockey_zsc() -> str:
    return (FIXTURES / "hockey_squad_sample_zsc.wikitext").read_text(encoding="utf-8")


def _load_hockey_zsc_article() -> str:
    return (FIXTURES / "hockey_article_sample_zsc.wikitext").read_text(encoding="utf-8")


def _load_player_infobox_en() -> str:
    return (FIXTURES / "player_infobox_en.wikitext").read_text(encoding="utf-8")


def _load_player_infobox_de() -> str:
    return (FIXTURES / "player_infobox_de.wikitext").read_text(encoding="utf-8")


def _load_player_infobox_hockey() -> str:
    return (FIXTURES / "player_infobox_hockey.wikitext").read_text(encoding="utf-8")


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


def test_parses_servette_first_team_subsection():
    # Servette nests "=== Die 1. Mannschaft ===" under "== Kader 2026/27 ==".
    # Either heading is enough on its own; here it exercises the first-team
    # subsection path plus dash-placeholder shirt numbers.
    players = parse_squad_players(_load_servette())
    name_set = {p.name for p in players}

    assert len(players) == 35
    assert "Edvinas Gertmonas" in name_set  # first row
    assert "Florian Ayé" in name_set  # last row

    # The "Staff/Betreuerstab" table is excluded by its heading ("betreuer").
    assert "Jocelyn Gourvennec" not in name_set
    assert "Alexandre Alphonse" not in name_set
    # The "Transfers 2026/27" bullet lists are excluded by heading ("transfer").
    assert "Jamie Atangana" not in name_set
    assert "Joel Mall" not in name_set


def test_servette_dash_number_is_none():
    players = {p.name: p for p in parse_squad_players(_load_servette())}

    # A "'''-'''" placeholder in the "Nr." column means no number assigned.
    assert players["Leart Zuka"].number is None
    assert players["Mattéo Anselme"].number is None
    assert players["Sidiki Camara"].number is None
    # Real numbers are unaffected.
    assert players["Edvinas Gertmonas"].number == "1"
    assert players["Samuel Mráz"].title == "Samuel Mráz (Fußballspieler)"


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


# --- Swiss/German ice hockey ({{Eishockeykader/Spieler}}) format ------------
#
# These clubs don't list a squad inline: the article transcludes a per-club
# navbox template (find_squad_template_title), and the actual roster lives in
# that template's own wikitext as one {{Eishockeykader/Spieler}} call per
# player, alongside a {{Eishockeykader/Kopf}} header, {{#ifeq:}} formatting
# noise, an {{Eishockeykader/Trainer}} coaching-staff box, and a trailing
# <noinclude> documentation block — none of which must be mistaken for a
# player.


def test_finds_transcluded_squad_template():
    title = find_squad_template_title(_load_hockey_zsc_article())
    assert title == "Navigationsleiste Kader der ZSC Lions"


def test_no_squad_template_found_in_inline_squad_article():
    # A football article with an inline squad has no such transclusion.
    assert find_squad_template_title(_load()) is None


def test_parses_eishockeykader_players():
    players = parse_squad_players(_load_hockey_zsc())
    names = {p.name for p in players}

    # 2 goalkeepers + 9 defencemen + 17 forwards = 28 players.
    assert len(players) == 28
    assert "Šimon Hrubec" in names
    assert "Johan Sundström" in names  # last entry

    # The header, coaching-staff box, and noinclude doc section must not
    # leak in as players.
    assert "Andreas Lilja" not in names
    assert "Fabio Schwarz" not in names
    assert "Sven Leuenberger" not in names


def test_eishockeykader_link_targets_numbers_and_positions():
    players = {p.name: p for p in parse_squad_players(_load_hockey_zsc())}

    # No explicit Link: default title is "Vorname Nachname".
    hrubec = players["Šimon Hrubec"]
    assert hrubec.title == "Šimon Hrubec"
    assert hrubec.number == "30"
    assert hrubec.position == "G"

    # Explicit Link overrides the default (disambiguated article title).
    lehtonen = players["Mikko Lehtonen"]
    assert lehtonen.title == "Mikko Lehtonen (Eishockeyspieler, 1994)"

    # Blank "Nummer" (no jersey number assigned yet) yields None, not "".
    assert players["Juho Lammikko"].number is None
    assert players["Harrison Schreiber"].number is None


# --- Player career history ({{Infobox football biography}}) -----------------
#
# Marc-Vivien Foé: five senior clubs, a single-year spell with no dash
# (Canon Yaoundé), and a loan marked by both a leading "→" and a trailing
# "(loan)" (Manchester City). Youth (youthyearsN/youthclubsN) and national
# team (nationalyearsN/nationalteamN) entries must not leak in as clubs.


def test_parses_english_infobox_career():
    spells = parse_career_spells(_load_player_infobox_en())
    by_club = {s.club_name: s for s in spells}

    assert len(spells) == 5
    assert set(by_club) == {
        "Canon Yaoundé",
        "Lens",
        "West Ham United",
        "Lyon",
        "Manchester City",
    }
    assert "Union de Garoua" not in by_club  # youth club
    assert "Cameroon" not in by_club  # national team
    assert "Cameroon U20" not in by_club


def test_english_infobox_single_year_spell():
    by_club = {s.club_name: s for s in parse_career_spells(_load_player_infobox_en())}

    # "years1 = 1994" (no dash) is a single-season spell.
    canon = by_club["Canon Yaoundé"]
    assert canon.start_year == 1994
    assert canon.end_year == 1994
    assert canon.ongoing is False
    assert canon.club_title == "Canon Yaoundé"


def test_english_infobox_loan_and_link_target():
    by_club = {s.club_name: s for s in parse_career_spells(_load_player_infobox_en())}

    lens = by_club["Lens"]
    assert lens.club_title == "RC Lens"
    assert lens.start_year == 1994
    assert lens.end_year == 1999
    assert lens.loan is False

    # Loan marked with a leading "→" and a trailing "(loan)" annotation; both
    # must be stripped from the display name and flagged.
    city = by_club["Manchester City"]
    assert city.club_title == "Manchester City F.C."
    assert city.start_year == 2002
    assert city.end_year == 2003
    assert city.loan is True


# --- Player career history ({{Infobox Fußballspieler}}) ----------------------
#
# Alain Nef: seven senior spells in "vereine_tabelle", including a
# single-year loan with padding whitespace and no dash (Recreativo Huelva),
# three explicit loans ("leihe=1"), and a repeat spell at the same club
# written as plain text the second time ("FC Zürich" with no wikilink).
# The youth ("jugendvereine_tabelle") and national team
# ("nationalmannschaft_tabelle") tables must not leak in.


def test_parses_german_infobox_career():
    spells = parse_career_spells(_load_player_infobox_de())
    assert len(spells) == 7

    names = [s.club_name for s in spells]
    assert names == [
        "FC Zürich",  # first spell, 2001-2006
        "Piacenza Calcio",
        "Udinese Calcio",
        "Recreativo Huelva",
        "US Triestina",
        "BSC Young Boys",
        "FC Zürich",
    ]
    # Youth/national-team tables must not be read as senior clubs.
    assert "FC Wädenswil" not in names
    assert "Schweiz U20" not in names
    assert "Schweiz" not in names


def test_german_infobox_link_targets_and_loans():
    spells = parse_career_spells(_load_player_infobox_de())
    first_fcz, piacenza, udinese, recreativo, triestina, byb, second_fcz = spells

    assert first_fcz.club_title == "FC Zürich"
    assert first_fcz.start_year == 2001
    assert first_fcz.end_year == 2006
    assert first_fcz.loan is False

    # Piped wikilink: display text differs from the article title.
    assert piacenza.club_title == "Lupa Piacenza"
    assert piacenza.club_name == "Piacenza Calcio"

    # "2009     " (padded, no dash) is a single-year loan spell.
    assert recreativo.start_year == 2009
    assert recreativo.end_year == 2009
    assert recreativo.loan is True

    assert triestina.loan is True
    assert byb.loan is True

    # The second FC Zürich spell is written as plain text (no wikilink).
    assert second_fcz.club_title is None
    assert second_fcz.club_name == "FC Zürich"
    assert second_fcz.start_year == 2013
    assert second_fcz.end_year == 2019
    assert second_fcz.loan is False


# --- Player career history: format with no per-club years --------------------
#
# {{Infobox ice hockey player}} only gives an overall career_start/career_end
# and a played_for list with no years per club, so it cannot be attributed to
# a specific club; parse_career_spells must not guess and returns [].


def test_hockey_infobox_has_no_attributable_career_years():
    assert parse_career_spells(_load_player_infobox_hockey()) == []


def test_parse_career_spells_handles_empty_input():
    assert parse_career_spells("") == []


def test_parse_career_spells_handles_no_infobox():
    assert parse_career_spells("Just some prose, no infobox at all.") == []
