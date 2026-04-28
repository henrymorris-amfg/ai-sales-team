from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
TARGET = OUTPUT_DIR / "dashboard.html"

AMFG_BLUE = "#1B83FF"
AMFG_DARK = "#272727"
AMFG_MUTED = "#646464"
AMFG_BORDER = "#EBEDF0"
AMFG_BG = "#F7F9FC"
AMFG_CARD = "#FFFFFF"


STATUS_STYLES = {
    "active": ("#E8F3FF", "#1B83FF"),
    "planned": ("#F1F3F5", "#646464"),
    "paused": ("#FFF3E8", "#C76B00"),
}



def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))



def _fmt_int(value: int) -> str:
    return f"{value:,}"



def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"



def _safe_get(row, key, default=None):
    value = row.get(key, default)
    return default if value is None else value



def build_dashboard() -> str:
    agents = _load_json(OUTPUT_DIR / "agent-status.json", [])
    findings = _load_json(OUTPUT_DIR / "findings.json", [])
    owners = _load_json(OUTPUT_DIR / "owner-summary.json", [])
    lead_samples = _load_json(OUTPUT_DIR / "cnc-lead-review-sample-5.json", [])
    lead_queue = _load_json(OUTPUT_DIR / "cnc-lead-review-queue-first-100.json", [])

    severity_counts = Counter((_safe_get(item, "severity", "unknown") or "unknown").lower() for item in findings)
    rule_counts = Counter(_safe_get(item, "rule_id", "unknown") for item in findings)
    stage_counts = Counter((item.get("evidence") or {}).get("stage_name", "Unknown") for item in findings)
    recommendation_counts = Counter(_safe_get(item, "recommendation", "unknown") for item in lead_samples)

    active_agents = sum(1 for agent in agents if _safe_get(agent, "status", "").lower() == "active")
    planned_agents = sum(1 for agent in agents if _safe_get(agent, "status", "").lower() == "planned")
    total_processed = sum(int(_safe_get(agent, "processed_today", 0) or 0) for agent in agents)
    total_queue = sum(int(_safe_get(agent, "queue_count", 0) or 0) for agent in agents)

    top_owners = sorted(owners, key=lambda row: int(_safe_get(row, "finding_count", 0) or 0), reverse=True)[:6]
    top_findings = findings[:8]
    top_rules = rule_counts.most_common(5)
    top_stages = [(name, count) for name, count in stage_counts.most_common(5) if name and name != "Unknown"]

    max_owner_findings = max([int(_safe_get(owner, "finding_count", 0) or 0) for owner in top_owners] or [1])

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    agent_cards = []
    for agent in agents:
        status = (_safe_get(agent, "status", "planned") or "planned").lower()
        bg, fg = STATUS_STYLES.get(status, ("#F1F3F5", "#646464"))
        agent_cards.append(
            f"""
            <article class=\"agent-card\">
              <div class=\"agent-card-top\">
                <div>
                  <div class=\"eyebrow\">{escape(_safe_get(agent, 'region', ''))}</div>
                  <h3>{escape(_safe_get(agent, 'name', 'Unknown agent'))}</h3>
                </div>
                <span class=\"pill\" style=\"background:{bg};color:{fg};\">{escape(status.title())}</span>
              </div>
              <p class=\"muted\">{escape(_safe_get(agent, 'scope', ''))}</p>
              <div class=\"agent-metrics\">
                <div><span>Queue</span><strong>{_fmt_int(int(_safe_get(agent, 'queue_count', 0) or 0))}</strong></div>
                <div><span>Processed</span><strong>{_fmt_int(int(_safe_get(agent, 'processed_today', 0) or 0))}</strong></div>
                <div><span>Errors</span><strong>{_fmt_int(int(_safe_get(agent, 'errors_today', 0) or 0))}</strong></div>
              </div>
            </article>
            """
        )

    owner_rows = []
    for owner in top_owners:
        finding_count = int(_safe_get(owner, "finding_count", 0) or 0)
        width = max(8, int((finding_count / max_owner_findings) * 100))
        owner_rows.append(
            f"""
            <div class=\"owner-row\">
              <div class=\"owner-meta\">
                <strong>{escape(_safe_get(owner, 'owner_name', 'Unassigned'))}</strong>
                <span>{escape(_safe_get(owner, 'owner_email', ''))}</span>
              </div>
              <div class=\"owner-bar-wrap\">
                <div class=\"owner-bar\" style=\"width:{width}%\"></div>
              </div>
              <strong>{_fmt_int(finding_count)}</strong>
            </div>
            """
        )

    finding_rows = []
    for finding in top_findings:
        severity = (_safe_get(finding, "severity", "unknown") or "unknown").lower()
        stage = escape(str((finding.get("evidence") or {}).get("stage_name", "No stage")))
        finding_rows.append(
            f"""
            <div class=\"finding-row\">
              <div class=\"finding-row-top\">
                <span class=\"rule\">{escape(_safe_get(finding, 'rule_id', ''))}</span>
                <span class=\"severity {escape(severity)}\">{escape(severity.title())}</span>
              </div>
              <div class=\"finding-summary\">{escape(_safe_get(finding, 'summary', ''))}</div>
              <div class=\"finding-foot\">{stage} • {escape(_safe_get(finding, 'suggested_action', ''))}</div>
            </div>
            """
        )

    lead_rows = []
    for lead in lead_samples[:5]:
        recommendation = _safe_get(lead, "recommendation", "unknown")
        confidence = float(_safe_get(lead, "confidence", 0.0) or 0.0)
        lead_rows.append(
            f"""
            <tr>
              <td>{escape(_safe_get(lead, 'title', ''))}</td>
              <td>{escape(recommendation.replace('_', ' ').title())}</td>
              <td>{_safe_get(lead, 'score', 0)}</td>
              <td>{_pct(confidence)}</td>
              <td>{escape(_safe_get(lead, 'website', ''))}</td>
            </tr>
            """
        )

    rule_rows = "".join(
        f"<div class=\"mini-stat\"><span>{escape(rule)}</span><strong>{_fmt_int(count)}</strong></div>"
        for rule, count in top_rules
    )

    stage_rows = "".join(
        f"<div class=\"mini-stat\"><span>{escape(stage)}</span><strong>{_fmt_int(count)}</strong></div>"
        for stage, count in top_stages
    ) or '<div class="mini-stat"><span>No stage data yet</span><strong>0</strong></div>'

    lead_mix_rows = "".join(
        f"<div class=\"mini-stat\"><span>{escape(name.replace('_', ' ').title())}</span><strong>{_fmt_int(count)}</strong></div>"
        for name, count in recommendation_counts.items()
    ) or '<div class="mini-stat"><span>No lead review sample yet</span><strong>0</strong></div>'

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>AMFG AI Sales Team Dashboard</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap\" rel=\"stylesheet\">
  <style>
    :root {{
      --blue: {AMFG_BLUE};
      --dark: {AMFG_DARK};
      --muted: {AMFG_MUTED};
      --border: {AMFG_BORDER};
      --bg: {AMFG_BG};
      --card: {AMFG_CARD};
      --success: #1f9d63;
      --warning: #c76b00;
      --danger: #cf3f3f;
      --shadow: 0 20px 50px rgba(27, 39, 51, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; background: linear-gradient(180deg, #f5f9ff 0%, var(--bg) 28%, #f8fafc 100%); color: var(--dark); }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 28px; }}
    .hero {{ background: radial-gradient(circle at top left, rgba(27,131,255,0.18), rgba(27,131,255,0) 40%), linear-gradient(135deg, #0f1720 0%, #1f2937 48%, #111827 100%); color: white; border-radius: 28px; padding: 32px; box-shadow: var(--shadow); position: relative; overflow: hidden; }}
    .hero::after {{ content: \"\"; position: absolute; inset: auto -80px -80px auto; width: 260px; height: 260px; border-radius: 50%; background: rgba(27,131,255,0.16); filter: blur(10px); }}
    .brand {{ display: flex; align-items: center; gap: 14px; font-weight: 700; letter-spacing: 0.02em; }}
    .brand-mark {{ width: 16px; height: 16px; background: var(--blue); border-radius: 5px; box-shadow: 20px 0 0 rgba(27,131,255,0.35), 40px 0 0 rgba(27,131,255,0.15); }}
    .hero-grid {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; margin-top: 28px; align-items: end; }}
    .hero h1 {{ margin: 10px 0 12px; font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1.02; max-width: 10ch; }}
    .hero p {{ margin: 0; color: rgba(255,255,255,0.78); max-width: 58ch; font-size: 1rem; }}
    .hero-panel {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.14); border-radius: 22px; padding: 18px; backdrop-filter: blur(10px); }}
    .hero-panel-title {{ color: rgba(255,255,255,0.7); font-size: .82rem; text-transform: uppercase; letter-spacing: .08em; }}
    .hero-panel strong {{ display: block; font-size: 2.4rem; margin-top: 8px; }}
    .hero-panel small {{ display: block; margin-top: 6px; color: rgba(255,255,255,0.7); }}
    .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; margin: 22px 0; }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 24px; box-shadow: var(--shadow); }}
    .kpi-card {{ padding: 22px; }}
    .label {{ color: var(--muted); font-size: .86rem; text-transform: uppercase; letter-spacing: .08em; }}
    .value {{ font-size: 2rem; font-weight: 800; margin-top: 10px; }}
    .subtle {{ color: var(--muted); margin-top: 6px; font-size: .93rem; }}
    .grid {{ display: grid; grid-template-columns: 1.45fr .95fr; gap: 18px; margin-top: 18px; }}
    .section {{ padding: 22px; }}
    .section h2 {{ margin: 0 0 4px; font-size: 1.2rem; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 18px; }}
    .section-head p {{ margin: 0; color: var(--muted); }}
    .agent-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }}
    .agent-card {{ border: 1px solid var(--border); border-radius: 20px; padding: 18px; background: linear-gradient(180deg, #fff 0%, #fcfdff 100%); }}
    .agent-card-top {{ display: flex; justify-content: space-between; gap: 14px; align-items: start; }}
    .agent-card h3 {{ margin: 4px 0 0; font-size: 1.05rem; }}
    .pill {{ display: inline-flex; border-radius: 999px; padding: 8px 12px; font-size: .82rem; font-weight: 700; }}
    .eyebrow {{ color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; }}
    .muted {{ color: var(--muted); line-height: 1.5; }}
    .agent-metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 16px; }}
    .agent-metrics div {{ background: var(--bg); border-radius: 16px; padding: 12px; }}
    .agent-metrics span {{ display: block; color: var(--muted); font-size: .78rem; margin-bottom: 6px; }}
    .agent-metrics strong {{ font-size: 1.15rem; }}
    .stack {{ display: grid; gap: 18px; }}
    .owner-row {{ display: grid; grid-template-columns: 1.3fr 1fr auto; gap: 12px; align-items: center; margin-bottom: 14px; }}
    .owner-meta {{ display: grid; gap: 4px; }}
    .owner-meta span {{ color: var(--muted); font-size: .88rem; }}
    .owner-bar-wrap {{ height: 10px; background: #edf2f7; border-radius: 999px; overflow: hidden; }}
    .owner-bar {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--blue), #6fb4ff); }}
    .finding-list {{ display: grid; gap: 12px; }}
    .finding-row {{ border: 1px solid var(--border); border-radius: 18px; padding: 16px; }}
    .finding-row-top {{ display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 10px; }}
    .rule {{ color: var(--blue); font-weight: 700; font-size: .84rem; letter-spacing: .06em; }}
    .severity {{ border-radius: 999px; padding: 6px 10px; font-size: .76rem; font-weight: 700; }}
    .severity.medium {{ background: #fff4e5; color: var(--warning); }}
    .severity.low {{ background: #eef6ef; color: var(--success); }}
    .severity.high {{ background: #ffebeb; color: var(--danger); }}
    .severity.unknown {{ background: #f1f3f5; color: var(--muted); }}
    .finding-summary {{ font-weight: 600; line-height: 1.45; }}
    .finding-foot {{ margin-top: 8px; color: var(--muted); font-size: .9rem; }}
    .mini-stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
    .mini-stat {{ background: var(--bg); border-radius: 18px; padding: 14px; }}
    .mini-stat span {{ display: block; color: var(--muted); font-size: .83rem; margin-bottom: 6px; }}
    .mini-stat strong {{ font-size: 1.2rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 14px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
    th {{ color: var(--muted); font-size: .82rem; text-transform: uppercase; letter-spacing: .08em; }}
    .footer {{ display: flex; justify-content: space-between; gap: 16px; color: var(--muted); padding: 16px 4px 0; font-size: .9rem; }}
    @media (max-width: 1100px) {{
      .hero-grid, .grid {{ grid-template-columns: 1fr; }}
      .kpis {{ grid-template-columns: repeat(2, 1fr); }}
      .agent-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 720px) {{
      .shell {{ padding: 16px; }}
      .hero {{ padding: 22px; border-radius: 22px; }}
      .kpis {{ grid-template-columns: 1fr; }}
      .mini-stats {{ grid-template-columns: 1fr; }}
      .owner-row {{ grid-template-columns: 1fr; }}
      .footer {{ flex-direction: column; }}
      th:nth-child(5), td:nth-child(5) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class=\"shell\">
    <section class=\"hero\">
      <div class=\"brand\"><div class=\"brand-mark\"></div><span>AMFG AI SALES TEAM</span></div>
      <div class=\"hero-grid\">
        <div>
          <h1>Manage the AI sales team in one place.</h1>
          <p>A simple AMFG-branded control view for Sales Ops, AI BDR USA & Canada, AI BDR UK & Ireland, and AI BDR EU. Built around the live Pipedrive hygiene outputs already running in the workspace.</p>
        </div>
        <div class=\"hero-panel\">
          <div class=\"hero-panel-title\">Current posture</div>
          <strong>{_fmt_int(active_agents)} live, {_fmt_int(planned_agents)} queued</strong>
          <small>{_fmt_int(total_queue)} items waiting across agents, {_fmt_int(total_processed)} processed in the current run.</small>
        </div>
      </div>
    </section>

    <section class=\"kpis\">
      <div class=\"card kpi-card\"><div class=\"label\">Open hygiene findings</div><div class=\"value\">{_fmt_int(len(findings))}</div><div class=\"subtle\">{_fmt_int(severity_counts.get('medium', 0))} medium, {_fmt_int(severity_counts.get('low', 0))} low</div></div>
      <div class=\"card kpi-card\"><div class=\"label\">Lead review queue</div><div class=\"value\">{_fmt_int(len(lead_queue))}</div><div class=\"subtle\">CNC-labelled leads prioritized for website-backed review</div></div>
      <div class=\"card kpi-card\"><div class=\"label\">Owners impacted</div><div class=\"value\">{_fmt_int(len(owners))}</div><div class=\"subtle\">Top reps and managers needing action right now</div></div>
      <div class=\"card kpi-card\"><div class=\"label\">Generated</div><div class=\"value\">{generated_at.split()[1]}</div><div class=\"subtle\">{generated_at.split()[0]} UTC snapshot</div></div>
    </section>

    <section class=\"grid\">
      <div class=\"card section\">
        <div class=\"section-head\">
          <div>
            <h2>Agent control surface</h2>
            <p>The first simple management layer for the four-agent model.</p>
          </div>
        </div>
        <div class=\"agent-grid\">{''.join(agent_cards)}</div>
      </div>

      <div class=\"stack\">
        <div class=\"card section\">
          <div class=\"section-head\"><div><h2>Owners needing attention</h2><p>Who currently has the biggest cleanup load.</p></div></div>
          {''.join(owner_rows) or '<p class="muted">No owner summary data yet.</p>'}
        </div>
        <div class=\"card section\">
          <div class=\"section-head\"><div><h2>Rule pressure</h2><p>Where the hygiene engine is firing most often.</p></div></div>
          <div class=\"mini-stats\">{rule_rows}</div>
        </div>
      </div>
    </section>

    <section class=\"grid\">
      <div class=\"card section\">
        <div class=\"section-head\"><div><h2>Priority findings</h2><p>The first issues worth acting on inside Pipedrive.</p></div></div>
        <div class=\"finding-list\">{''.join(finding_rows)}</div>
      </div>
      <div class=\"stack\">
        <div class=\"card section\">
          <div class=\"section-head\"><div><h2>Deal stage hotspots</h2><p>Which stages are producing the most issues.</p></div></div>
          <div class=\"mini-stats\">{stage_rows}</div>
        </div>
        <div class=\"card section\">
          <div class=\"section-head\"><div><h2>Lead review mix</h2><p>Sample output from the CNC lead-review worker.</p></div></div>
          <div class=\"mini-stats\">{lead_mix_rows}</div>
        </div>
      </div>
    </section>

    <section class=\"card section\" style=\"margin-top:18px;\">
      <div class=\"section-head\"><div><h2>CNC lead sample</h2><p>Quick view of the reviewed leads and their current recommendation state.</p></div></div>
      <table>
        <thead>
          <tr><th>Lead</th><th>Recommendation</th><th>Score</th><th>Confidence</th><th>Website</th></tr>
        </thead>
        <tbody>
          {''.join(lead_rows) or '<tr><td colspan="5">No lead sample data yet.</td></tr>'}
        </tbody>
      </table>
    </section>

    <div class=\"footer\">
      <div>Designed to feel like AMFG, using Inter plus the website palette cues, especially the AMFG blue and charcoal.</div>
      <div>Next natural upgrade: convert this into a live React dashboard with action controls and refreshable APIs.</div>
    </div>
  </div>
</body>
</html>
"""
    return html



def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(build_dashboard(), encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
