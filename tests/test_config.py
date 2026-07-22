import pytest
from conftest import FIXTURES  # noqa: F401  (ensures src on sys.path)

from wd_squads.config import load_config


def _write(tmp_path, text):
    path = tmp_path / "cfg.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_leagues(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
user_agent: "wd-squads-test/0.1 (mailto:me@here.org)"
leagues:
  - id: Q9448
    label: Premier League
""",
        )
    )
    assert cfg.leagues[0].id == "Q9448"
    assert cfg.leagues[0].label == "Premier League"
    assert not cfg.has_explicit_teams()


def test_per_league_language_with_fallback(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
language: en
user_agent: "wd-squads-test/0.1 (mailto:me@here.org)"
leagues:
  - id: Q331268
    language: de
  - id: Q9448
""",
        )
    )
    # Explicit per-league language is kept...
    assert cfg.leagues[0].language == "de"
    # ...and a league without one falls back to the global default.
    assert cfg.leagues[1].language == "en"


def test_per_league_team_class_with_fallback(tmp_path):
    # QIDs below are arbitrary placeholders chosen only to exercise the
    # override/fallback logic, not real Wikidata classes.
    cfg = load_config(
        _write(
            tmp_path,
            """
user_agent: "wd-squads-test/0.1 (mailto:me@here.org)"
team_class: Q476028
leagues:
  - id: Q331268
    team_class: Q999001
  - id: Q9448
""",
        )
    )
    # Explicit per-league team_class is kept...
    assert cfg.leagues[0].team_class == "Q999001"
    # ...and a league without one falls back to the config-level default.
    assert cfg.leagues[1].team_class == "Q476028"


def test_default_team_class_is_football(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
user_agent: "wd-squads-test/0.1 (mailto:me@here.org)"
leagues:
  - id: Q9448
""",
        )
    )
    assert cfg.team_class == "Q476028"
    assert cfg.leagues[0].team_class == "Q476028"


def test_explicit_teams(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
user_agent: "wd-squads-test/0.1 (mailto:me@here.org)"
teams:
  - Q18500
""",
        )
    )
    assert cfg.has_explicit_teams()
    assert cfg.teams == ["Q18500"]


def test_requires_a_source(tmp_path):
    with pytest.raises(ValueError):
        load_config(
            _write(tmp_path, 'user_agent: "wd-squads-test/0.1 (mailto:me@here.org)"')
        )


def test_rejects_placeholder_user_agent(tmp_path):
    with pytest.raises(ValueError):
        load_config(
            _write(
                tmp_path,
                """
user_agent: "bot (https://example.com)"
teams:
  - Q1
""",
            )
        )
