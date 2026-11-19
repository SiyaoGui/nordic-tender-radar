"""Build the Nordic Tender Radar website from TED (official EU procurement data).

Runs daily in GitHub Actions. Fetches open calls for tender from the Nordic
countries, writes static HTML pages into docs/ (served by GitHub Pages).
Usage: python site/build.py [--fixture path.json] [--out docs]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
import time
import urllib.request
from pathlib import Path

API_URL = "https://api.ted.europa.eu/v3/notices/search"
SITE_URL = "https://siyaogui.github.io/nordic-tender-radar"
ACTOR_URL = "https://apify.com/nordic-tender-radar/eu-tender-finder"
BRAND = "Nordic Tender Radar"
DAYS = 21
MAX_PER_PAGE = 150

COUNTRIES = [
    ("denmark", "Denmark", "DNK"),
    ("sweden", "Sweden", "SWE"),
    ("norway", "Norway", "NOR"),
    ("finland", "Finland", "FIN"),
    ("iceland", "Iceland", "ISL"),
]
SECTORS = [
    ("it-software", "IT and software", ("72", "48")),
    ("construction", "Construction and building works", ("45",)),
    ("cleaning-facility", "Cleaning and facility services", ("909", "907", "797", "983")),
    ("medical-health", "Medical equipment and health", ("33", "85")),
    ("consulting", "Consulting and business services", ("79", "73", "71")),
    ("transport-vehicles", "Transport and vehicles", ("60", "34")),
    ("energy-environment", "Energy and environment", ("09", "31", "90")),
]
FIELDS = [
    "publication-number", "notice-type", "notice-title", "buyer-name", "buyer-country",
    "publication-date", "deadline-receipt-tender-date-lot", "estimated-value-lot",
    "estimated-value-cur-lot", "classification-cpv", "procedure-type",
]
OPEN_TYPES = "cn-standard cn-social cn-desg subco pin-cfc-standard pin-cfc-social"


# ---------------------------------------------------------------- data
def fetch_notices(today: dt.date) -> list[dict]:
    since = today - dt.timedelta(days=DAYS - 1)
    iso3 = " ".join(c[2] for c in COUNTRIES)
    query = (
        f"publication-date>={since:%Y%m%d} AND buyer-country IN ({iso3}) "
        f"AND notice-type IN ({OPEN_TYPES}) AND deadline-receipt-tender-date-lot>={today:%Y%m%d} "
        "SORT BY publication-date DESC"
    )
    out: list[dict] = []
    for page in range(1, 41):
        body = json.dumps({"query": query, "fields": FIELDS, "page": page, "limit": 250,
                           "paginationMode": "PAGE_NUMBER"}).encode()
        data = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(API_URL, data=body, method="POST",
                                             headers={"Content-Type": "application/json",
                                                      "User-Agent": "nordic-tender-radar-site"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.load(resp)
                break
            except Exception as exc:  # network hiccup, retry
                print(f"TED page {page} attempt {attempt + 1} failed: {exc}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        if data is None:
            raise RuntimeError("TED API unreachable")
        notices = data.get("notices") or []
        out.extend(notices)
        if len(notices) < 250:
            break
    return out


def pick(value, langs=("eng", "dan", "swe", "nor", "fin")):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "; ".join(dict.fromkeys(str(v) for v in value if v))
    if isinstance(value, dict):
        for lang in langs:
            if value.get(lang):
                return pick(value[lang], langs)
        for v in value.values():
            if v:
                return pick(v, langs)
    return ""


def uniq(values) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    return list(dict.fromkeys(str(v) for v in values if v not in (None, "")))


def shape(n: dict) -> dict | None:
    pub = n.get("publication-number")
    if not pub:
        return None
    deadlines = sorted(d[:10] for d in uniq(n.get("deadline-receipt-tender-date-lot")))
    values = []
    for v in n.get("estimated-value-lot") or []:
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            pass
    currencies = uniq(n.get("estimated-value-cur-lot"))
    title = pick(n.get("notice-title"))
    # TED titles start with "Country – CPV description – actual title"; keep the useful part.
    parts = [p.strip() for p in title.split(" – ")]
    short = parts[-1] if len(parts) >= 3 else title
    category = parts[1] if len(parts) >= 3 else ""
    return {
        "id": pub,
        "title": short or title,
        "category": category,
        "buyer": pick(n.get("buyer-name")),
        "country": (uniq(n.get("buyer-country")) or [""])[0],
        "published": (uniq(n.get("publication-date")) or [""])[0][:10],
        "deadline": deadlines[0] if deadlines else "",
        "value": round(sum(values)) if values else None,
        "currency": currencies[0] if len(currencies) == 1 else "",
        "cpv": uniq(n.get("classification-cpv")),
        "url": f"https://ted.europa.eu/en/notice/-/detail/{pub}",
    }


# ---------------------------------------------------------------- html
CSS = """
:root{--bg:#fbfaf7;--fg:#1d2026;--muted:#5d6470;--line:#e3e1da;--card:#ffffff;--accent:#0f5d7a;--accent-ink:#ffffff;--chip:#eef4f6}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--fg:#e9e7e2;--muted:#a3a8b1;--line:#2a2e35;--card:#1a1d22;--accent:#5fb3cf;--accent-ink:#0c1215;--chip:#1f2a30}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header.top{border-bottom:1px solid var(--line)}
header.top .wrap{display:flex;gap:16px;align-items:center;justify-content:space-between;min-height:60px;flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.2px;text-decoration:none;color:var(--fg)}
nav a{margin-right:14px;text-decoration:none;color:var(--muted);font-size:15px}
.hero{padding:44px 0 20px}
.hero h1{font-size:clamp(28px,4.4vw,42px);line-height:1.15;margin:0 0 12px;max-width:820px}
.hero p{color:var(--muted);max-width:720px;margin:0 0 20px;font-size:18px}
.btn{display:inline-block;background:var(--accent);color:var(--accent-ink);padding:11px 18px;border-radius:8px;text-decoration:none;font-weight:600}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent);margin-left:8px}
.stats{display:flex;gap:28px;flex-wrap:wrap;margin:26px 0 8px;color:var(--muted)}
.stats b{display:block;font-size:26px;color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:14px 0 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;text-decoration:none;color:var(--fg)}
.card span{color:var(--muted);font-size:14px}
h2{font-size:22px;margin:34px 0 10px}
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.tbl th,.tbl td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:15px}
.tbl th{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}
.tbl td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.tbl .cat{display:block;color:var(--muted);font-size:13px}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 8px;font-size:12px;color:var(--muted)}
.scroll{overflow-x:auto}
.cta{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:30px 0}
.cta h3{margin:0 0 6px}
footer{border-top:1px solid var(--line);margin-top:40px;padding:22px 0 40px;color:var(--muted);font-size:14px}
@media (max-width:640px){.tbl thead{display:none}.tbl tr{display:block;border-bottom:1px solid var(--line)}.tbl td{display:block;border:0;padding:4px 12px}.tbl td:first-child{padding-top:12px}.tbl td:last-child{padding-bottom:12px}.tbl td.num{text-align:left}.btn.ghost{margin:8px 0 0}}
"""


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def fmt_value(t: dict) -> str:
    if not t["value"]:
        return "<span class=chip>not stated</span>"
    v = t["value"]
    txt = f"{v/1e6:.1f}M" if v >= 1e6 else (f"{v/1e3:.0f}k" if v >= 1e3 else f"{v:.0f}")
    return f"{txt} {esc(t['currency'])}"


def table(items: list[dict], show_country=True) -> str:
    if not items:
        return "<p>No open tenders right now. TED publishes on weekdays, so check back tomorrow.</p>"
    rows = []
    for t in items[:MAX_PER_PAGE]:
        rows.append(
            "<tr>"
            f"<td><a href='{esc(t['url'])}' rel='nofollow noopener' target='_blank'>{esc(t['title'])}</a>"
            f"<span class=cat>{esc(t['category'])}</span></td>"
            f"<td>{esc(t['buyer'])}</td>"
            + (f"<td>{esc(t['country'])}</td>" if show_country else "")
            + f"<td class=num>{esc(t['deadline'])}</td>"
            f"<td class=num>{fmt_value(t)}</td>"
            "</tr>"
        )
    head = ("<tr><th>Tender</th><th>Buyer</th>" + ("<th>Country</th>" if show_country else "")
            + "<th>Deadline</th><th>Est. value</th></tr>")
    more = ""
    if len(items) > MAX_PER_PAGE:
        more = (f"<p>Showing the {MAX_PER_PAGE} newest of {len(items)}. "
                f"<a href='{ACTOR_URL}'>Get the full list as a spreadsheet or API</a>.</p>")
    return f"<div class=scroll><table class=tbl><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>{more}"


def cta() -> str:
    return (
        "<div class=cta><h3>Get new tenders as a daily alert</h3>"
        "<p>Pick your countries, keywords and CPV codes once. Every morning you get only the new "
        "tenders that match, as a spreadsheet, email or straight into your CRM. Pay a fraction of a cent per tender, "
        "no subscription.</p>"
        f"<a class=btn href='{ACTOR_URL}'>Set up my tender alert</a></div>"
    )


def page(title: str, desc: str, body: str, path: str, updated: str) -> str:
    canonical = f"{SITE_URL}/{path}" if path != "index.html" else f"{SITE_URL}/"
    nav = "".join(f"<a href='{slug}.html'>{name}</a>" for slug, name, _ in COUNTRIES[:4])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:type" content="website">
<style>{CSS}</style></head><body>
<header class=top><div class=wrap><a class=brand href="index.html">{BRAND}</a><nav>{nav}</nav></div></header>
<main class=wrap>{body}</main>
<footer><div class=wrap>Updated {esc(updated)} from TED, the official EU public procurement journal.
Source: &copy; European Union, <a href="https://ted.europa.eu">ted.europa.eu</a>, reused under the Commission's open data policy.
Always check the official notice before bidding. {BRAND} is an independent service, not affiliated with the EU.</div></footer>
</body></html>"""


def plural(n: int) -> str:
    return f"{n} open tender" + ("" if n == 1 else "s")


def sector_of(t: dict) -> list[str]:
    out = []
    for slug, _, prefixes in SECTORS:
        if any(c.startswith(p) for c in t["cpv"] for p in prefixes):
            out.append(slug)
    return out


def build(notices: list[dict], out: Path, today: dt.date) -> dict:
    items = [s for s in (shape(n) for n in notices) if s]
    seen, tenders = set(), []
    for t in items:
        if t["id"] not in seen:
            seen.add(t["id"])
            tenders.append(t)
    tenders.sort(key=lambda t: (t["published"], t["id"]), reverse=True)
    updated = f"{today:%d %B %Y}"
    out.mkdir(parents=True, exist_ok=True)
    pages = ["index.html"]
    by_country = {iso: [t for t in tenders if t["country"] == iso] for _, _, iso in COUNTRIES}
    by_sector = {slug: [t for t in tenders if slug in sector_of(t)] for slug, _, _ in SECTORS}

    for slug, name, iso in COUNTRIES:
        lst = by_country[iso]
        body = (f"<section class=hero><h1>Open public tenders in {name}</h1>"
                f"<p>{len(lst)} calls for tender from public buyers in {name} that are still open for bids, "
                f"published on TED in the last {DAYS} days. Updated every day.</p></section>"
                + table(lst, show_country=False) + cta())
        (out / f"{slug}.html").write_text(page(
            f"Open public tenders in {name} ({len(lst)} today) | {BRAND}",
            f"{len(lst)} open public procurement tenders in {name} from TED, with buyer, deadline and value. Updated daily.",
            body, f"{slug}.html", updated), encoding="utf-8")
        pages.append(f"{slug}.html")

    for slug, name, _ in SECTORS:
        lst = by_sector[slug]
        body = (f"<section class=hero><h1>Nordic public tenders: {name.lower()}</h1>"
                f"<p>{len(lst)} open calls for tender in {name.lower()} from Denmark, Sweden, Norway, Finland and Iceland. "
                f"Updated every day from TED.</p></section>" + table(lst) + cta())
        (out / f"{slug}.html").write_text(page(
            f"Nordic {name.lower()} tenders ({len(lst)} open) | {BRAND}",
            f"{len(lst)} open public tenders for {name.lower()} in the Nordic countries, from official TED data. Updated daily.",
            body, f"{slug}.html", updated), encoding="utf-8")
        pages.append(f"{slug}.html")

    total_value = sum(t["value"] or 0 for t in tenders if t["currency"] in ("EUR",))
    country_cards = "".join(
        f"<a class=card href='{slug}.html'><b>{name}</b><br><span>{plural(len(by_country[iso]))}</span></a>"
        for slug, name, iso in COUNTRIES)
    sector_cards = "".join(
        f"<a class=card href='{slug}.html'><b>{name}</b><br><span>{plural(len(by_sector[slug]))}</span></a>"
        for slug, name, _ in SECTORS)
    body = (
        "<section class=hero><h1>Every open public tender in the Nordics, in one place.</h1>"
        "<p>Public buyers in Denmark, Sweden, Norway, Finland and Iceland publish thousands of contracts a year. "
        "We collect the ones you can still bid on, every day, and send you only the new ones that fit your business.</p>"
        f"<a class=btn href='{ACTOR_URL}'>Get daily tender alerts</a>"
        "<a class='btn ghost' href='#latest'>See today's tenders</a>"
        f"<div class=stats><div><b>{len(tenders)}</b>open tenders</div>"
        f"<div><b>{sum(1 for t in tenders if t['published'] >= (today - dt.timedelta(days=6)).isoformat())}</b>published this week</div>"
        + (f"<div><b>EUR {total_value/1e6:,.0f}M</b>stated value (EUR notices)</div>" if total_value else "")
        + "</div></section>"
        f"<h2>By country</h2><div class=grid>{country_cards}</div>"
        f"<h2>By sector</h2><div class=grid>{sector_cards}</div>"
        "<h2 id=latest>Newest open tenders</h2>" + table(tenders[:40]) + cta()
        + "<h2>How it works</h2><p>Every EU public buyer above the EU thresholds must publish on TED, the official journal. "
        "We read TED every day, keep the notices that are still open, clean them up and translate the titles to English. "
        f"For alerts and full exports we run the same search for you on <a href='{ACTOR_URL}'>Apify</a>: filter by keyword in "
        "any language, country, CPV code, value and deadline, and get a spreadsheet, JSON or API feed.</p>"
    )
    (out / "index.html").write_text(page(
        f"Nordic public tenders today ({len(tenders)} open) | {BRAND}",
        "Every open public tender in Denmark, Sweden, Norway, Finland and Iceland, updated daily from TED. Daily alerts by keyword, country and CPV code.",
        body, "index.html", updated), encoding="utf-8")

    urls = "".join(f"<url><loc>{SITE_URL}/{p if p != 'index.html' else ''}</loc><lastmod>{today.isoformat()}</lastmod></url>"
                   for p in pages)
    (out / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "data.json").write_text(json.dumps({"updated": today.isoformat(), "count": len(tenders),
                                               "by_country": {k: len(v) for k, v in by_country.items()}}),
                                   encoding="utf-8")
    return {"tenders": len(tenders), "pages": len(pages)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture")
    ap.add_argument("--out", default="docs")
    ap.add_argument("--today")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    notices = json.loads(Path(args.fixture).read_text()) if args.fixture else fetch_notices(today)
    stats = build(notices, Path(args.out), today)
    print(f"Built {stats['pages']} pages with {stats['tenders']} open tenders")
    if not args.fixture and stats["tenders"] == 0 and today.weekday() < 5:
        print("No tenders found on a weekday; something may be wrong", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
