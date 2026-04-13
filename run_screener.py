#!/usr/bin/env python3
"""
Daniel's Breakout Daily Screener
Calls the local FastAPI backend at localhost:8000, generates a dark HTML report,
and emails it to danielkim009@gmail.com.

Usage:
  python3 run_screener.py            # run screen + send email
  python3 run_screener.py --no-email # run screen, skip email

Requirements:
  - Stock screener backend running:  cd backend && .venv/bin/uvicorn app.main:app --port 8000
  - Gmail App Password saved at:     ~/.screener_config.json
"""

from __future__ import annotations

import argparse
import json
import smtplib
import sys
import urllib.error
import urllib.request
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
API_BASE     = "http://localhost:8000/api"
UNIVERSE     = "sp500"
MIN_CRITERIA = 5          # 5+ criteria (matches the "5+ criteria" dropdown)
MAX_TICKERS  = 3000       # All tickers (matches "All (~503)" in the UI)
OUTPUT_DIR   = Path.home() / "Documents" / "stock-screen-reports"
CONFIG_FILE  = Path.home() / ".screener_config.json"
EMAIL_TO     = "danielkim009@gmail.com"
MAX_RESULTS  = 20
API_TIMEOUT  = 300        # 5 minutes — the screen can take a while


# ── Fetch results from FastAPI backend ───────────────────────────────────────
def fetch_results() -> dict:
    url = (
        f"{API_BASE}/screen/daniels"
        f"?universe={UNIVERSE}"
        f"&min_criteria={MIN_CRITERIA}"
        f"&max_tickers={MAX_TICKERS}"
    )
    print(f"  API: {url}")
    try:
        with urllib.request.urlopen(url, timeout=API_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"\nERROR: Cannot reach backend at {API_BASE}.")
        print(f"  Make sure uvicorn is running:  cd /Users/tastymaster/cline/stock-screeners/backend")
        print(f"  Then run:  .venv/bin/uvicorn app.main:app --port 8000")
        print(f"  Details: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR fetching results: {exc}")
        sys.exit(1)


# ── HTML helpers ──────────────────────────────────────────────────────────────
def badge(passed: bool, label: str) -> str:
    cls = "pass" if passed else "fail"
    return f'<span class="badge {cls}">{label}</span>'


def fmt_vol(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(int(v))


# ── Generate dark-themed HTML report ─────────────────────────────────────────
def generate_html(data: dict, report_date: str) -> str:
    results = data["results"][:MAX_RESULTS]
    total   = data["total_screened"]
    matches = data["matches"]
    shown   = len(results)

    rows = []
    for i, r in enumerate(results, 1):
        met = r["criteria_met"]
        met_color = "#56d364" if met == 6 else "#e3b341"

        pct = r.get("price_change_pct")
        if pct is not None:
            pct_str   = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
            pct_color = "#56d364" if pct > 0 else ("#f85149" if pct < 0 else "#8b949e")
        else:
            pct_str, pct_color = "—", "#8b949e"

        rv = r.get("rel_volume", 0)
        rv_color = "#56d364" if rv >= 2 else ("#e3b341" if rv >= 1.5 else "#8b949e")

        rows.append(f"""        <tr>
          <td class="rank">{i}</td>
          <td class="ticker-cell">
            <span class="ticker">{r["ticker"]}</span>
            <span class="name">{r.get("name") or ""}</span>
          </td>
          <td style="color:{pct_color}">{pct_str}</td>
          <td>${r["last_close"]:.2f}</td>
          <td style="color:{rv_color}">{rv:.1f}×</td>
          <td style="font-size:12px;color:#8b949e">{fmt_vol(r.get("today_vol"))}</td>
          <td>{badge(r["c1"], "C1")}</td>
          <td>{badge(r["c2"], "C2")}</td>
          <td>{badge(r["c3"], "C3")}</td>
          <td>{badge(r["c4"], "C4")}</td>
          <td>{badge(r["c5"], "C5")}</td>
          <td>{badge(r["c6"], "C6")}</td>
          <td><strong style="color:{met_color}">{met}/6</strong></td>
        </tr>""")

    rows_html = "\n".join(rows) if rows else (
        '<tr><td colspan="13" style="text-align:center;color:#8b949e;padding:32px">'
        'No stocks met 5+ criteria today</td></tr>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daniel's Breakout Screen — {report_date}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",monospace;padding:24px}}
  h1{{font-size:22px;margin-bottom:6px}}
  .meta{{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:#8b949e;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #21262d}}
  .stats{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
  .stat{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px 16px;min-width:110px}}
  .stat .lbl{{font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}}
  .stat .val{{font-size:20px;font-weight:700}}
  .legend{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px 14px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:#8b949e}}
  .legend strong{{color:#58a6ff}}
  table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden}}
  th{{padding:8px 12px;text-align:left;border-bottom:1px solid #30363d;color:#8b949e;font-size:11px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;background:#0d1117}}
  td{{padding:8px 12px;border-bottom:1px solid #21262d;font-size:13px}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#1c2128}}
  .rank{{color:#8b949e;font-size:12px;width:30px}}
  .ticker-cell{{white-space:nowrap}}
  .ticker{{font-weight:700;color:#58a6ff}}
  .name{{display:block;font-size:11px;color:#8b949e;font-weight:400}}
  .badge{{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700}}
  .badge.pass{{background:#1a3a1a;color:#56d364;border:1px solid #2a5a2a}}
  .badge.fail{{background:#1c2128;color:#484f58;border:1px solid #30363d}}
  .source{{font-size:12px;color:#8b949e;margin-top:14px;padding:8px 12px;background:#161b22;border:1px solid #21262d;border-radius:6px}}
  .footer{{margin-top:16px;font-size:11px;color:#484f58;border-top:1px solid #21262d;padding-top:12px}}
</style>
</head>
<body>
<h1>📈 Daniel's Breakout Screen</h1>
<div class="meta">
  <span>📅 {report_date}</span>
  <span>🌎 S&amp;P 500</span>
  <span>🎯 Min: 5+ criteria</span>
  <span>🔝 Top {MAX_RESULTS} shown</span>
</div>

<div class="stats">
  <div class="stat"><div class="lbl">Screened</div><div class="val" style="color:#e6edf3">{total}</div></div>
  <div class="stat"><div class="lbl">Full Passes (6/6)</div><div class="val" style="color:#56d364">{matches}</div></div>
  <div class="stat"><div class="lbl">Shown (5–6/6)</div><div class="val" style="color:#e3b341">{shown}</div></div>
</div>

<div class="legend">
  <strong>C1</strong> Price &gt; EMA21 &nbsp;
  <strong>C2</strong> EMA21 ≥ EMA50 &nbsp;
  <strong>C3</strong> EMA50 ≥ EMA100 &nbsp;
  <strong>C4</strong> New 6-month high &nbsp;
  <strong>C5</strong> Rel Vol ≥ 1.5× &nbsp;
  <strong>C6</strong> 10d avg vol ≥ 1M
</div>

<table>
  <thead>
    <tr>
      <th>#</th><th>Ticker</th><th>Chg %</th><th>Close</th>
      <th>Rel Vol</th><th>Volume</th>
      <th>C1</th><th>C2</th><th>C3</th><th>C4</th><th>C5</th><th>C6</th>
      <th>Met</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>

<div class="source">
  ✅ Source: localhost:8000/api — same Python backend as the browser app at localhost:5175
</div>

<div class="footer">
  Generated {report_date} · For educational and research purposes only · Not financial advice
</div>
</body>
</html>"""


# ── Send email ────────────────────────────────────────────────────────────────
def send_email(report_path: Path, data: dict, report_date: str) -> None:
    if not CONFIG_FILE.exists():
        print(f"\nERROR: Config not found at {CONFIG_FILE}")
        print("Run setup.sh to configure Gmail credentials, or create it manually:")
        print('  {"email": {"sender": "you@gmail.com", "app_password": "xxxx xxxx xxxx xxxx", '
              '"smtp_server": "smtp.gmail.com", "smtp_port": 587}}')
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        cfg = json.load(f)["email"]

    results = data["results"][:MAX_RESULTS]
    matches = data["matches"]
    shown   = len(results)

    subject = f"📈 Breakout Report — {report_date} | {shown} stocks ({matches} with 6/6)"

    # Top-10 summary table for email body
    rows = []
    for i, r in enumerate(results[:10], 1):
        met = r["criteria_met"]
        color = "#56d364" if met == 6 else "#e3b341"
        pct   = r.get("price_change_pct")
        pct_s = (f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%") if pct is not None else "—"
        pct_c = "#56d364" if (pct or 0) > 0 else ("#f85149" if (pct or 0) < 0 else "#8b949e")
        rows.append(
            f'<tr>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #21262d;font-weight:700;color:#58a6ff">{r["ticker"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #21262d">${r["last_close"]:.2f}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #21262d;color:{pct_c}">{pct_s}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #21262d;font-weight:700;color:{color}">{met}/6</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #21262d;color:#8b949e">{r.get("rel_volume",0):.1f}×</td>'
            f'</tr>'
        )
    rows_html = "\n".join(rows) if rows else (
        '<tr><td colspan="5" style="padding:12px;color:#8b949e;text-align:center">No results today</td></tr>'
    )
    more_note = (
        f'<p style="color:#8b949e;font-size:12px;margin-top:8px">…and {shown - 10} more in the attached report</p>'
        if shown > 10 else ""
    )

    body = f"""<html><body style="background:#0d1117;color:#e6edf3;font-family:-apple-system,sans-serif;padding:24px;max-width:600px">
<h2 style="color:#e6edf3;margin-bottom:6px">📈 Daniel's Breakout — {report_date}</h2>
<p style="color:#8b949e;font-size:13px;margin-bottom:16px">S&amp;P 500 · Min 5+ criteria · {data["total_screened"]} tickers screened</p>
<table style="border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;width:100%;max-width:500px">
  <thead>
    <tr style="background:#0d1117">
      <th style="padding:7px 10px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase">Ticker</th>
      <th style="padding:7px 10px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase">Close</th>
      <th style="padding:7px 10px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase">Chg %</th>
      <th style="padding:7px 10px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase">Criteria</th>
      <th style="padding:7px 10px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase">Rel Vol</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
{more_note}
<p style="color:#484f58;font-size:11px;margin-top:20px">Full report attached · For educational purposes only · Not financial advice</p>
</body></html>"""

    msg = MIMEMultipart("mixed")
    msg["From"]    = cfg["sender"]
    msg["To"]      = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(report_path.read_bytes())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{report_path.name}"')
    msg.attach(part)

    print(f"  Sending to {EMAIL_TO} ...")
    with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as s:
        s.starttls()
        s.login(cfg["sender"], cfg["app_password"])
        s.send_message(msg)
    print("  Email sent ✓")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Daniel's Breakout Daily Screener")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    args = parser.parse_args()

    report_date = date.today().strftime("%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"breakout-report-{report_date}.html"

    print(f"=== Daniel's Breakout Screener — {report_date} ===")

    # 1. Fetch from backend
    print("Step 1: Fetching results from API ...")
    data    = fetch_results()
    results = data["results"][:MAX_RESULTS]
    print(f"  Screened {data['total_screened']} tickers, "
          f"{data['matches']} full passes (6/6), "
          f"{len(results)} shown (5–6/6)")

    # 2. Generate HTML report
    print("Step 2: Generating HTML report ...")
    html = generate_html(data, report_date)
    report_path.write_text(html, encoding="utf-8")
    print(f"  Saved: {report_path}")

    # 3. Email (unless --no-email)
    if not args.no_email:
        print("Step 3: Sending email ...")
        send_email(report_path, data, report_date)
    else:
        print("Step 3: Email skipped (--no-email)")

    # 4. Summary
    print("\n=== Summary ===")
    if results:
        top5 = ", ".join(r["ticker"] for r in results[:5])
        print(f"  Top 5 tickers: {top5}")
        print(f"  Full passes (6/6): {data['matches']}")
        print(f"  Report: {report_path}")
    else:
        print("  No stocks met 5+ criteria today.")


if __name__ == "__main__":
    main()
