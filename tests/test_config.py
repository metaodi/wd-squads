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
