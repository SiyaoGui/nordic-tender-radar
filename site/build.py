"""Build the Tendernord website from TED (official EU procurement data).

Runs every morning in GitHub Actions. Fetches calls for tender from the Nordic
countries that are still open, and writes static pages into docs/ (GitHub Pages).
Usage: python site/build.py [--fixture path.json] [--out docs] [--today YYYY-MM-DD]
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
ACTOR_URL = "https://apify.com/tendernord/eu-tender-finder"
ISSUES_URL = "https://apify.com/tendernord/eu-tender-finder/issues"
BRAND = "Tendernord"
CONTACT_EMAIL = "alicesnack0225@gmail.com"
DAYS = 30
SERVER_ROWS = 60  # rows rendered into the HTML; the rest load from tenders.json

COUNTRIES = [
    ("denmark", "Denmark", "DNK", "Danmark"),
    ("sweden", "Sweden", "SWE", "Sverige"),
    ("norway", "Norway", "NOR", "Norge"),
    ("finland", "Finland", "FIN", "Suomi"),
    ("iceland", "Iceland", "ISL", "Ísland"),
]
COUNTRY_NAME = {iso: name for _, name, iso, _ in COUNTRIES}
SECTORS = [
    ("it-software", "IT and software", ("72", "48")),
    ("construction", "Construction", ("45",)),
    ("cleaning-facility", "Cleaning and facility services", ("909", "907", "797", "983")),
    ("medical-health", "Medical and health", ("33", "85")),
    ("consulting", "Consulting and engineering", ("79", "73", "71")),
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


def sectors_for(cpv: list[str]) -> list[str]:
    return [slug for slug, _, prefixes in SECTORS if any(c.startswith(p) for c in cpv for p in prefixes)]


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
    # TED titles read "Country – CPV description – buyer's own title".
    parts = [p.strip() for p in title.split(" – ")]
    own = " – ".join(parts[2:]) if len(parts) >= 3 else title
    category = parts[1] if len(parts) >= 3 else ""
    cpv = uniq(n.get("classification-cpv"))
    return {
        "id": pub,
        "t": own or title,
        "c": category,
        "b": pick(n.get("buyer-name")),
        "n": (uniq(n.get("buyer-country")) or [""])[0],
        "p": (uniq(n.get("publication-date")) or [""])[0][:10],
        "d": deadlines[0] if deadlines else "",
        "v": round(sum(values)) if values else None,
        "u": currencies[0] if len(currencies) == 1 else "",
        "s": sectors_for(cpv),
    }


# ---------------------------------------------------------------- html
CSS = """
:root{--paper:#f6f4ef;--ink:#1c1b19;--soft:#5b5852;--rule:#d8d3c7;--row:#fffdf8;--hi:#8f2d22;--hi-bg:#f3e3df;--focus:#1c1b19}
@media (prefers-color-scheme:dark){:root{--paper:#151514;--ink:#ecebe6;--soft:#a29f97;--rule:#33312d;--row:#1c1c1a;--hi:#e58b7c;--hi-bg:#3a2522;--focus:#ecebe6}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
a{color:inherit}
.w{max-width:1120px;margin:0 auto;padding:0 16px}
.mast{border-bottom:2px solid var(--ink)}
.mast .w{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:16px;padding-bottom:10px}
.logo{font:700 21px/1.1 Georgia,"Iowan Old Style","Times New Roman",serif;text-decoration:none;letter-spacing:-.2px}
.logo small{display:block;font:12px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:var(--soft);letter-spacing:.3px;margin-top:3px}
.mast nav a{font-size:14px;text-decoration:none;margin-left:18px;color:var(--soft)}
.mast nav a[aria-current]{color:var(--ink);text-decoration:underline;text-underline-offset:4px}
.sub{border-bottom:1px solid var(--rule);font-size:13px;color:var(--soft)}
.sub .w{display:flex;gap:16px;flex-wrap:wrap;padding-top:7px;padding-bottom:7px}
.sub a{text-decoration:none}.sub a:hover{text-decoration:underline}
h1{font:700 26px/1.2 Georgia,"Iowan Old Style","Times New Roman",serif;margin:26px 0 6px;letter-spacing:-.2px}
.lede{color:var(--soft);margin:0 0 18px;max-width:760px}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin-bottom:4px}
.filters input,.filters select{font:inherit;font-size:14px;color:var(--ink);background:var(--row);border:1px solid var(--rule);border-radius:3px;padding:6px 8px;min-width:0}
.filters input{flex:1 1 220px}
.filters select{flex:0 1 auto}
.filters :focus{outline:2px solid var(--focus);outline-offset:1px}
.count{font-size:13px;color:var(--soft);padding:8px 0}
ol.list{list-style:none;margin:0;padding:0;border-top:1px solid var(--rule)}
.item{display:grid;grid-template-columns:1fr 150px 120px;gap:4px 18px;padding:11px 0;border-bottom:1px solid var(--rule)}
.item:hover{background:var(--row)}
.ttl{font-weight:600;text-decoration:none}.ttl:hover{text-decoration:underline}
.meta{font-size:13px;color:var(--soft);grid-column:1}
.dl,.val{font-size:14px;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.dl small,.val small{display:block;font-size:12px;color:var(--soft)}
.dl.soon{color:var(--hi)}.dl.soon small{color:var(--hi)}
.colhead{display:grid;grid-template-columns:1fr 150px 120px;gap:18px;font-size:12px;color:var(--soft);text-transform:uppercase;letter-spacing:.6px;padding:6px 0}
.colhead span:not(:first-child){text-align:right}
.more{margin:16px 0;font-size:14px}
button.more{font:inherit;font-size:14px;background:none;border:1px solid var(--ink);color:var(--ink);padding:7px 14px;border-radius:3px;cursor:pointer}
.prose{max-width:700px}
.prose h2{font:700 19px/1.3 Georgia,"Iowan Old Style","Times New Roman",serif;margin:28px 0 6px}
.prose p,.prose li{margin:0 0 10px}
.price{border:1px solid var(--rule);background:var(--row);padding:14px 16px;margin:14px 0;max-width:700px}
.price b{font-size:20px}
.btn{display:inline-block;background:var(--ink);color:var(--paper);text-decoration:none;padding:9px 16px;border-radius:3px;font-weight:600;font-size:14px}
pre{background:var(--row);border:1px solid var(--rule);padding:12px;overflow-x:auto;font-size:12.5px;line-height:1.45}
.note{font-size:13px;color:var(--soft)}
.cta{border:1px solid var(--ink);background:var(--row);padding:16px 18px;margin:0 0 30px;max-width:760px}
.cta h2{font:700 18px/1.3 Georgia,"Iowan Old Style","Times New Roman",serif;margin:0 0 6px}
.cta p{margin:0 0 12px}
.cta .note{margin:10px 0 0}
h2.sec{font:700 20px/1.3 Georgia,"Iowan Old Style","Times New Roman",serif;margin:0 0 6px}
footer{border-top:1px solid var(--rule);margin-top:44px;padding:18px 0 40px;font-size:13px;color:var(--soft)}
footer p{margin:0 0 6px;max-width:760px}
@media (max-width:700px){
 .item,.colhead{grid-template-columns:1fr auto}
 .colhead span:nth-child(3),.item .val{display:none}
 .mast nav a{margin:0 14px 0 0}
 .mast nav{width:100%}
}
"""

JS = """
(function(){
 var list=document.getElementById('list'); if(!list) return;
 var preset=JSON.parse(list.getAttribute('data-preset')||'{}');
 var q=document.getElementById('q'),fc=document.getElementById('fc'),fs=document.getElementById('fs'),fd=document.getElementById('fd'),so=document.getElementById('so');
 var cnt=document.getElementById('count'),more=document.getElementById('more');
 var data=null,shown=60,today=list.getAttribute('data-today');
 var names=JSON.parse(list.getAttribute('data-countries'));
 function days(d){return Math.round((Date.parse(d)-Date.parse(today))/864e5);}
 function money(v,u){if(!v)return '';var s=v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?Math.round(v/1e3)+'k':String(v);return s+' '+(u||'');}
 function esc(s){return String(s||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
 function row(t){var n=days(t.d);var soon=n<=7?' soon':'';
  return '<li class="item"><div><a class="ttl" target="_blank" rel="noopener" href="https://ted.europa.eu/en/notice/-/detail/'+esc(t.id)+'">'+esc(t.t)+'</a>'+
  '<div class="meta">'+esc(t.b)+' &middot; '+esc(names[t.n]||t.n)+(t.c?' &middot; '+esc(t.c):'')+'</div></div>'+
  '<div class="dl'+soon+'">'+esc(t.d)+'<small>'+(n<=0?'today':n===1?'1 day left':n+' days left')+'</small></div>'+
  '<div class="val">'+(t.v?esc(money(t.v,t.u)):'<small>value not stated</small>')+'</div></li>';}
 function apply(){ if(!data) return;
  var text=(q.value||'').toLowerCase().trim(),c=fc.value,s=fs.value,d=parseInt(fd.value||'0',10);
  var out=data.filter(function(t){
   if(c&&t.n!==c) return false; if(s&&t.s.indexOf(s)<0) return false;
   if(d&&days(t.d)>d) return false;
   if(text&&(t.t+' '+t.b+' '+t.c).toLowerCase().indexOf(text)<0) return false; return true;});
  var k=so.value;
  out.sort(function(a,b){ if(k==='deadline') return a.d<b.d?-1:a.d>b.d?1:0; if(k==='value') return (b.v||0)-(a.v||0); return a.p<b.p?1:a.p>b.p?-1:0;});
  cnt.textContent=out.length+' open tender'+(out.length===1?'':'s');
  list.innerHTML=out.slice(0,shown).map(row).join('');
  more.hidden=out.length<=shown;
 }
 [q,fc,fs,fd,so].forEach(function(el){el.addEventListener(el===q?'input':'change',function(){shown=60;apply();});});
 more.addEventListener('click',function(){shown+=60;apply();});
 fetch(list.getAttribute('data-src')).then(function(r){return r.json();}).then(function(j){data=j;
  if(preset.c){fc.value=preset.c;} if(preset.s){fs.value=preset.s;} apply();}).catch(function(){});
})();
"""


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def money(v, u) -> str:
    if not v:
        return ""
    s = f"{v/1e6:.1f}M" if v >= 1e6 else (f"{round(v/1e3)}k" if v >= 1e3 else str(v))
    return f"{s} {u}".strip()


def days_left(deadline: str, today: dt.date) -> int:
    try:
        return (dt.date.fromisoformat(deadline) - today).days
    except ValueError:
        return 999


def row_html(t: dict, today: dt.date) -> str:
    n = days_left(t["d"], today)
    left = "today" if n <= 0 else ("1 day left" if n == 1 else f"{n} days left")
    meta = f"{esc(t['b'])} &middot; {esc(COUNTRY_NAME.get(t['n'], t['n']))}" + (f" &middot; {esc(t['c'])}" if t["c"] else "")
    val = esc(money(t["v"], t["u"])) if t["v"] else "<small>value not stated</small>"
    return (f"<li class=item><div><a class=ttl target=_blank rel=noopener "
            f"href='https://ted.europa.eu/en/notice/-/detail/{esc(t['id'])}'>{esc(t['t'])}</a>"
            f"<div class=meta>{meta}</div></div>"
            f"<div class='dl{' soon' if n <= 7 else ''}'>{esc(t['d'])}<small>{left}</small></div>"
            f"<div class=val>{val}</div></li>")


def filters_html(preset: dict) -> str:
    copts = "".join(f"<option value='{iso}'{' selected' if preset.get('c') == iso else ''}>{name}</option>"
                    for _, name, iso, _ in COUNTRIES)
    sopts = "".join(f"<option value='{slug}'{' selected' if preset.get('s') == slug else ''}>{name}</option>"
                    for slug, name, _ in SECTORS)
    return (
        "<div class=filters role=search>"
        "<input id=q type=search placeholder='Search title, buyer or category (any language)' aria-label='Search tenders'>"
        f"<select id=fc aria-label='Country'><option value=''>All countries</option>{copts}</select>"
        f"<select id=fs aria-label='Sector'><option value=''>All sectors</option>{sopts}</select>"
        "<select id=fd aria-label='Deadline'><option value=''>Any deadline</option><option value='7'>Closes within 7 days</option>"
        "<option value='14'>Within 14 days</option><option value='30'>Within 30 days</option></select>"
        "<select id=so aria-label='Sort'><option value='new'>Newest first</option><option value='deadline'>Deadline soonest</option>"
        "<option value='value'>Highest value</option></select></div>"
    )


def listing(items: list[dict], today: dt.date, preset: dict) -> str:
    rows = "".join(row_html(t, today) for t in items[:SERVER_ROWS])
    countries = json.dumps({iso: name for _, name, iso, _ in COUNTRIES})
    return (
        filters_html(preset)
        + f"<div class=count id=count>{len(items)} open tender{'' if len(items) == 1 else 's'}</div>"
        + "<div class=colhead aria-hidden=true><span>Tender</span><span>Deadline</span><span>Est. value</span></div>"
        + f"<ol class=list id=list data-src='tenders.json' data-today='{today.isoformat()}' "
          f"data-preset='{esc(json.dumps(preset))}' data-countries='{esc(countries)}'>{rows}</ol>"
        + f"<button class=more id=more{' hidden' if len(items) <= SERVER_ROWS else ''}>Show more</button>"
    )


def page(title: str, desc: str, body: str, path: str, today: dt.date, active: str = "") -> str:
    canonical = f"{SITE_URL}/{path}" if path != "index.html" else f"{SITE_URL}/"
    nav = "".join(
        f"<a href='{href}'{' aria-current=page' if key == active else ''}>{label}</a>"
        for key, href, label in (("tenders", "index.html", "Tenders"), ("alerts", "alerts.html", "Alerts and API"),
                                 ("about", "about.html", "About")))
    sub = "".join(f"<a href='{slug}.html'>{name}</a>" for slug, name, _, _ in COUNTRIES) + \
          "".join(f"<a href='{slug}.html'>{name}</a>" for slug, name, _ in SECTORS[:4])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:type" content="website">
<style>{CSS}</style></head><body>
<header class=mast><div class=w><a class=logo href="index.html">{BRAND}<small>Public contracts in the Nordic countries</small></a><nav>{nav}</nav></div></header>
<div class=sub><div class=w>{sub}</div></div>
<main class=w>{body}</main>
<footer><div class=w>
<p>Updated {today:%d %B %Y}. Notices come from TED, the EU's official journal for public procurement (&copy; European Union, reused under the Commission's open data policy). Titles are TED's English versions where one exists; read the official notice before you bid.</p>
<p>{BRAND} is an independent service based in Copenhagen and is not part of the EU or any public authority.</p>
</div></footer>
<script>{JS}</script>
</body></html>"""


def build(notices: list[dict], out: Path, today: dt.date) -> dict:
    seen, tenders = set(), []
    for t in (shape(n) for n in notices):
        if t and t["id"] not in seen:
            seen.add(t["id"])
            tenders.append(t)
    tenders.sort(key=lambda t: (t["p"], t["id"]), reverse=True)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):
        old.unlink()
    (out / "tenders.json").write_text(json.dumps(tenders, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    pages = []

    def write(name, html_text):
        (out / name).write_text(html_text, encoding="utf-8")
        pages.append(name)

    week = sum(1 for t in tenders if t["p"] >= (today - dt.timedelta(days=6)).isoformat())
    mailto = f"mailto:{CONTACT_EMAIL}?subject=Contract%20overview%20request"
    body = (f"<h1>Who holds which public contracts in the Nordics, and when they come up again</h1>"
            f"<p class=lede>{BRAND} reads the contract award notices on TED and keeps track of who holds which public contract "
            f"in Denmark, Sweden, Norway, Finland and Iceland, what it was awarded for and when it is tendered again.</p>"
            f"<div class=cta><h2>Free contract overview for your area</h2>"
            f"<p>Tell us your trade and your region. We send you one page with the public contracts held there today: "
            f"buyer, current supplier, award value and award date, each with its TED notice number. "
            f"The contract term is included where the notice states it.</p>"
            f"<a class=btn href='{mailto}'>Request your free overview</a>"
            f"<p class=note>Or write to <a href='mailto:{CONTACT_EMAIL}'>{CONTACT_EMAIL}</a>.</p></div>"
            f"<h2 class=sec id=tenders>Open tenders today</h2>"
            f"<p class=lede>{len(tenders)} calls for tender from public buyers in Denmark, Sweden, Norway, Finland and Iceland "
            f"that still accept bids. {week} of them were published in the last seven days. The list is rebuilt from TED every morning.</p>"
            + listing(tenders, today, {}))
    write("index.html", page(f"Who holds Nordic public contracts and when they are tendered again | {BRAND}",
                             "Who holds which public contract in Denmark, Sweden, Norway, Finland and Iceland, what it was awarded for and when it comes up again. "
                             f"Plus {len(tenders)} open tenders from TED, updated every morning.",
                             body, "index.html", today, "tenders"))

    for slug, name, iso, local in COUNTRIES:
        lst = [t for t in tenders if t["n"] == iso]
        body = (f"<h1>Open public tenders in {name}</h1>"
                f"<p class=lede>{len(lst)} calls for tender from public buyers in {name} ({local}) that still accept bids, "
                f"published on TED in the last {DAYS} days.</p>" + listing(lst, today, {"c": iso}))
        write(f"{slug}.html", page(f"Public tenders in {name}: {len(lst)} open | {BRAND}",
                                   f"{len(lst)} open public tenders in {name} from TED, with buyer, deadline and value. Updated every morning.",
                                   body, f"{slug}.html", today))

    for slug, name, _ in SECTORS:
        lst = [t for t in tenders if slug in t["s"]]
        body = (f"<h1>{name}: open public tenders in the Nordics</h1>"
                f"<p class=lede>{len(lst)} open calls for tender in {name.lower()} from Nordic public buyers. "
                f"The sector is matched on the CPV codes the buyer chose, so check the notice for the exact scope.</p>"
                + listing(lst, today, {"s": slug}))
        write(f"{slug}.html", page(f"{name} tenders in the Nordics: {len(lst)} open | {BRAND}",
                                   f"{len(lst)} open public tenders in {name.lower()} in Denmark, Sweden, Norway, Finland and Iceland. Updated every morning.",
                                   body, f"{slug}.html", today))

    alerts = f"""<div class=prose>
<h1>Alerts and API</h1>
<p class=lede>The list on this site is free. If you want the tenders that match your business delivered every morning, or the full data as a spreadsheet or API feed, use our tender finder on Apify.</p>
<h2>What you set up once</h2>
<p>Keywords in any language (for example <i>rengøring</i>, <i>städning</i> or <i>cloud</i>), the countries you sell to, CPV codes if you use them, and a minimum contract value if small jobs are not worth your time. Then add a daily schedule in Apify.</p>
<h2>What you get each morning</h2>
<p>Only the notices that are new since the last run, one row per tender: title, buyer, buyer email, deadline, estimated value, CPV codes, the place of performance and links to the TED notice and the tender documents. Apify can send them to email, Slack, Google Sheets or your CRM.</p>
<pre>{{
  "title": "Denmark – Supply services of personnel including temporary staff – ...",
  "buyerName": "Region Hovedstaden",
  "submissionDeadline": "2026-12-17",
  "estimatedValue": 224000000,
  "currency": "DKK",
  "cpvCodes": ["79620000", "85311000"],
  "tedUrl": "https://ted.europa.eu/en/notice/-/detail/790080-2026"
}}</pre>
<h2>Price</h2>
<div class=price><b>$0.003 per tender delivered</b><br>No subscription. A daily alert for one sector in one country usually returns a handful of tenders a day, which is a few cents. Runs that find nothing new cost close to nothing. Apify adds its own small platform fee and has a free monthly allowance.</div>
<p><a class=btn href="{ACTOR_URL}">Open the tender finder on Apify</a></p>
<h2>Coverage</h2>
<p>All notices on TED, which covers contracts above the EU thresholds from every EU and EEA country. Smaller national tenders that only appear on national portals such as udbud.dk or Doffin are not included yet.</p>
<p class=note>Questions or a missing filter: write to us through the <a href="{ISSUES_URL}">Apify issues page</a>.</p>
</div>"""
    write("alerts.html", page(f"Tender alerts and API | {BRAND}",
                              "Daily alerts for new public tenders in the Nordics and the EU, by keyword, country and CPV code. $0.003 per tender, no subscription.",
                              alerts, "alerts.html", today, "alerts"))

    about = f"""<div class=prose>
<h1>About</h1>
<p>{BRAND} is a small, independent service in Copenhagen. We make public procurement data from the Nordic countries easy to search and easy to act on.</p>
<p>Public buyers in the EU must publish larger contracts on TED, the EU's official journal. The data is public, but it is spread over 24 languages and hard to filter, so small companies often miss contracts they could have won. This site lists every Nordic notice that is still open, and the tender finder on Apify turns the same data into daily alerts and exports.</p>
<h2>Where the data comes from</h2>
<p>Every listing comes from the official TED search service of the Publications Office of the European Union. We do not edit notices. We shorten titles, pick the English translation where TED has one, and add sector labels based on CPV codes.</p>
<h2>Contact</h2>
<p>Write to us through the <a href="{ISSUES_URL}">Apify issues page</a> for the tender finder.</p>
</div>"""
    write("about.html", page(f"About | {BRAND}", f"{BRAND} is an independent Copenhagen service for Nordic public tender data.",
                             about, "about.html", today, "about"))

    urls = "".join(f"<url><loc>{SITE_URL}/{p if p != 'index.html' else ''}</loc><lastmod>{today.isoformat()}</lastmod></url>"
                   for p in pages)
    (out / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "data.json").write_text(json.dumps({"updated": today.isoformat(), "count": len(tenders),
                                               "by_country": {iso: sum(1 for t in tenders if t["n"] == iso)
                                                              for _, _, iso, _ in COUNTRIES}}), encoding="utf-8")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
