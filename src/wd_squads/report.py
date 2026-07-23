"""Render the TODO list as Markdown files, a JSON dump and an HTML dashboard."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment

from .models import KIND_LABEL, PRIORITY, Suggestion, Team


@dataclass
class TeamResult:
    """Everything we learned about one team during a run."""

    team: Team
    suggestions: List[Suggestion] = field(default_factory=list)
    squad_size: int = 0
    wikidata_current: int = 0
    error: Optional[str] = None


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    return re.sub(r"[\s_-]+", "-", text) or "team"


def team_filename(team: Team) -> str:
    return f"{team.qid}-{_slug(team.label)}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --- Markdown ---------------------------------------------------------------
def render_team_markdown(result: TeamResult, generated_at: str) -> str:
    team = result.team
    lines = [
        f"# {team.label} — Wikidata squad TODO",
        "",
        f"- Wikidata item: [{team.qid}](https://www.wikidata.org/wiki/{team.qid})",
    ]
    if team.wikipedia_title:
        wp = team.wikipedia_title.replace(" ", "_")
        lines.append(
            f"- Wikipedia article: [{team.wikipedia_title}]"
            f"(https://{team.language}.wikipedia.org/wiki/{wp})"
        )
    lines += [
        f"- Players in Wikipedia squad: {result.squad_size}",
        f"- Current members on Wikidata: {result.wikidata_current}",
        f"- Suggested edits: {len(result.suggestions)}",
        f"- Generated: {generated_at}",
        "",
    ]

    if result.error:
        lines += [f"> ⚠️ Could not fully process this team: {result.error}", ""]

    if not result.suggestions:
        lines += ["✅ Nothing to do — Wikipedia and Wikidata agree.", ""]
        return "\n".join(lines)

    grouped: dict[str, List[Suggestion]] = {}
    for s in sorted(result.suggestions, key=lambda x: (x.priority, x.player_label.lower())):
        grouped.setdefault(s.kind, []).append(s)

    for kind in sorted(grouped, key=lambda k: PRIORITY.get(k, 99)):
        lines.append(f"## {KIND_LABEL.get(kind, kind)} ({len(grouped[kind])})")
        lines.append("")
        for s in grouped[kind]:
            lines.append(f"- {_markdown_player(s)} — {s.detail}")
        lines.append("")
    return "\n".join(lines)


def _markdown_player(s: Suggestion) -> str:
    if s.player_qid:
        name = f"**[{s.player_label}](https://www.wikidata.org/wiki/{s.player_qid})**"
    else:
        name = f"**{s.player_label}**"
    wp_url = s.links.get("wikipedia")
    if wp_url:
        name += f" ([WP]({wp_url}))"
    if s.years_label:
        name += f" ({s.years_label})"
    return name


def _group_by_league(results: List[TeamResult]) -> List[tuple[str, List[TeamResult]]]:
    """Bucket results by ``team.league``, teams without one under "Other".

    Leagues are ordered alphabetically, with "Other" always last.
    """
    buckets: dict[str, List[TeamResult]] = {}
    for r in results:
        buckets.setdefault(r.team.league or "Other", []).append(r)
    return sorted(buckets.items(), key=lambda kv: (kv[0] == "Other", kv[0].lower()))


def render_index_markdown(results: List[TeamResult], generated_at: str) -> str:
    total = sum(len(r.suggestions) for r in results)
    leagues = _group_by_league(results)
    lines = [
        "# wd-squads — suggested Wikidata edits",
        "",
        f"Generated: {generated_at}",
        "",
        f"**{total} suggested edits** across **{len(results)} teams**.",
        "",
    ]

    lines.append("## Leagues")
    lines.append("")
    for league_name, league_results in leagues:
        n = len(league_results)
        lines.append(f"- [{league_name}](#{_slug(league_name)}) ({n} team{'' if n == 1 else 's'})")
    lines.append("")

    for league_name, league_results in leagues:
        lines.append(f"## {league_name}")
        lines.append("")
        lines.append("| Team | Squad | WD current | Suggestions | Report |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for r in sorted(league_results, key=lambda x: (-len(x.suggestions), x.team.label.lower())):
            link = team_filename(r.team)
            lines.append(
                f"| [{r.team.label}](https://www.wikidata.org/wiki/{r.team.qid}) "
                f"| {r.squad_size} | {r.wikidata_current} | {len(r.suggestions)} "
                f"| [details]({link}) |"
            )
        lines.append("")
    return "\n".join(lines)


# --- JSON -------------------------------------------------------------------
def to_json(results: List[TeamResult], generated_at: str) -> dict:
    return {
        "generated": generated_at,
        "total_suggestions": sum(len(r.suggestions) for r in results),
        "teams": [
            {
                "qid": r.team.qid,
                "label": r.team.label,
                "league": r.team.league,
                "wikipedia_title": r.team.wikipedia_title,
                "squad_size": r.squad_size,
                "wikidata_current": r.wikidata_current,
                "error": r.error,
                "suggestions": [
                    {
                        "kind": s.kind,
                        "player": s.player_label,
                        "player_qid": s.player_qid,
                        "wikipedia_title": s.wikipedia_title,
                        "detail": s.detail,
                        "start_year": s.start_year,
                        "end_year": s.end_year,
                        "links": s.links,
                    }
                    for s in r.suggestions
                ],
            }
            for r in results
        ],
    }


# --- HTML dashboard ---------------------------------------------------------
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wd-squads — Wikidata squad TODO</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#1b1b1b; --muted:#666;
    --card:#f6f6f6; --border:#e2e2e2; --accent:#3366cc; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#14161a; --fg:#e8e8e8; --muted:#9aa0a6; --card:#1e2127;
      --border:#2c2f36; --accent:#7aa2f7; }
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg); color:var(--fg); line-height:1.5; }
  .wrap { max-width:960px; margin:0 auto; padding:1.5rem 1rem 4rem; }
  h1 { margin:0 0 .25rem; font-size:1.6rem; }
  .sub { color:var(--muted); margin:0 0 1.5rem; }
  .totals { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.5rem; }
  .stat { background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:.75rem 1rem; min-width:120px; }
  .stat b { font-size:1.5rem; display:block; }
  .league-nav { display:flex; flex-wrap:wrap; gap:.5rem; margin-bottom:1.5rem; }
  .league-nav a { background:var(--card); border:1px solid var(--border);
    border-radius:999px; padding:.3rem .8rem; font-size:.9rem; }
  .league { margin-bottom:2rem; }
  .league h2 { font-size:1.2rem; border-bottom:1px solid var(--border);
    padding-bottom:.3rem; scroll-margin-top:1rem; }
  .team { border:1px solid var(--border); border-radius:10px; margin-bottom:1rem;
    background:var(--card); overflow:hidden; }
  .team > summary { cursor:pointer; padding:.9rem 1rem; font-weight:600;
    display:flex; justify-content:space-between; align-items:center; gap:1rem; }
  .team > summary::-webkit-details-marker { display:none; }
  .count { background:var(--accent); color:#fff; border-radius:999px;
    padding:.1rem .6rem; font-size:.8rem; font-weight:600; }
  .count.zero { background:#3aa657; }
  .body { padding:0 1rem 1rem; }
  .kind { margin:1rem 0 .3rem; font-size:.95rem; color:var(--muted);
    text-transform:uppercase; letter-spacing:.03em; }
  ul { margin:.2rem 0 .6rem; padding-left:1.2rem; }
  li { margin:.35rem 0; }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }
  .detail { color:var(--muted); }
  footer { color:var(--muted); font-size:.85rem; margin-top:2rem; }
  code { background:var(--card); padding:.05rem .3rem; border-radius:4px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>wd-squads &mdash; suggested Wikidata edits</h1>
  <p class="sub">Football squads on Wikipedia vs. membership data (P54) on
     Wikidata. Generated {{ generated_at }}.</p>

  <div class="totals">
    <div class="stat"><b>{{ total }}</b> suggested edits</div>
    <div class="stat"><b>{{ results|length }}</b> teams checked</div>
    <div class="stat"><b>{{ teams_with_todos }}</b> teams need attention</div>
  </div>

  <nav class="league-nav">
    {% for league_name, league_slug, league_results in leagues %}
    <a href="#{{ league_slug }}">{{ league_name }}
      ({{ league_results|length }} {{ 'team' if league_results|length == 1 else 'teams' }})</a>
    {% endfor %}
  </nav>

  {% for league_name, league_slug, league_results in leagues %}
  <section class="league">
    <h2 id="{{ league_slug }}">{{ league_name }}</h2>
    {% for r in league_results %}
    <details class="team" {% if r.suggestions %}open{% endif %}>
      <summary>
        <span><a href="https://www.wikidata.org/wiki/{{ r.team.qid }}">{{ r.team.label }}</a>
          <span class="detail">&nbsp;{{ r.team.qid }}</span></span>
        <span class="count {% if not r.suggestions %}zero{% endif %}">
          {{ r.suggestions|length }} to&nbsp;do</span>
      </summary>
      <div class="body">
        <p class="detail">Squad on Wikipedia: {{ r.squad_size }} &middot;
          current members on Wikidata: {{ r.wikidata_current }}
          {% if r.error %}&middot; <strong>error:</strong> {{ r.error }}{% endif %}</p>
        {% if not r.suggestions %}
          <p>✅ Nothing to do &mdash; Wikipedia and Wikidata agree.</p>
        {% else %}
          {% for kind, items in r.grouped %}
          <div class="kind">{{ kind_label[kind] }} ({{ items|length }})</div>
          <ul>
            {% for s in items %}
            <li>
              {% if s.player_qid %}<a href="https://www.wikidata.org/wiki/{{ s.player_qid }}">{{ s.player_label }}</a>
              {% else %}<strong>{{ s.player_label }}</strong>{% endif %}
              {% if s.links.wikipedia %}(<a href="{{ s.links.wikipedia }}">WP</a>){% endif %}
              {% if s.years_label %}<span class="detail">&nbsp;({{ s.years_label }})</span>{% endif %}
              <span class="detail">&mdash; {{ s.detail }}</span>
            </li>
            {% endfor %}
          </ul>
          {% endfor %}
        {% endif %}
      </div>
    </details>
    {% endfor %}
  </section>
  {% endfor %}

  <footer>
    Built by <a href="https://github.com/metaodi/wd-squads">wd-squads</a>.
    Suggestions are heuristics &mdash; always verify before editing Wikidata.
  </footer>
</div>
</body>
</html>
"""


def render_html(results: List[TeamResult], generated_at: str) -> str:
    env = Environment(autoescape=True)
    template = env.from_string(_HTML_TEMPLATE)

    def grouped(result: TeamResult):
        buckets: dict[str, List[Suggestion]] = {}
        for s in sorted(result.suggestions, key=lambda x: (x.priority, x.player_label.lower())):
            buckets.setdefault(s.kind, []).append(s)
        return sorted(buckets.items(), key=lambda kv: PRIORITY.get(kv[0], 99))

    leagues = []
    for league_name, league_results in _group_by_league(results):
        ordered = sorted(
            league_results, key=lambda r: (-len(r.suggestions), r.team.label.lower())
        )
        for r in ordered:
            r.grouped = grouped(r)  # type: ignore[attr-defined]
        leagues.append((league_name, _slug(league_name), ordered))

    return template.render(
        leagues=leagues,
        results=results,
        generated_at=generated_at,
        total=sum(len(r.suggestions) for r in results),
        teams_with_todos=sum(1 for r in results if r.suggestions),
        kind_label=KIND_LABEL,
    )


# --- Orchestration ----------------------------------------------------------
def write_reports(
    results: List[TeamResult],
    reports_dir: str | Path,
    docs_dir: str | Path,
    generated_at: Optional[str] = None,
) -> None:
    generated_at = generated_at or now_iso()
    reports_dir = Path(reports_dir)
    docs_dir = Path(docs_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    (reports_dir / "README.md").write_text(
        render_index_markdown(results, generated_at), encoding="utf-8"
    )
    for r in results:
        (reports_dir / team_filename(r.team)).write_text(
            render_team_markdown(r, generated_at), encoding="utf-8"
        )

    (docs_dir / "index.html").write_text(
        render_html(results, generated_at), encoding="utf-8"
    )
    (docs_dir / "data.json").write_text(
        json.dumps(to_json(results, generated_at), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
