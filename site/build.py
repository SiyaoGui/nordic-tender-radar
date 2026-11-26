"""Build the Tendernord website from TED (official EU procurement data).

Runs every morning in GitHub Actions. Fetches open calls for tender and recent
contract award notices from the Nordic countries, and writes static pages into
docs/ (GitHub Pages).
Usage: python site/build.py [--fixture path.json] [--awards-fixture path.json]
                            [--out docs] [--today YYYY-MM-DD]
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
SERVER_ROWS = 60  # rows rendered into the HTML; the rest load from the json files
PRICE_FILE = 99  # EUR, one competitor file
PRICE_SUB = 49   # EUR per month, one trade in one region

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
    ("waste-recycling", "Waste and recycling", ("905",)),
    ("facility-maintenance", "Facility maintenance", ("507", "7033", "79993")),
    ("security", "Security services", ("7971",)),
    ("catering", "Catering and food services", ("553", "555")),
    ("passenger-transport", "Passenger transport", ("6011", "6012", "6013", "6014", "6017")),
    ("medical-health", "Medical and health", ("33", "85")),
    ("consulting", "Consulting and engineering", ("79", "73", "71")),
    ("transport-vehicles", "Transport and vehicles", ("60", "34")),
    ("energy-environment", "Energy and environment", ("09", "31", "90")),
]
# Sector pages linked in the bar under the header. Every sector page is linked from tenders.html.
SUBNAV_SECTORS = ("cleaning-facility", "waste-recycling", "facility-maintenance", "security", "catering",
                  "passenger-transport")
FIELDS = [
    "publication-number", "notice-type", "notice-title", "buyer-name", "buyer-country",
    "publication-date", "deadline-receipt-tender-date-lot", "estimated-value-lot",
    "estimated-value-cur-lot", "classification-cpv", "procedure-type",
]
OPEN_TYPES = "cn-standard cn-social cn-desg subco pin-cfc-standard pin-cfc-social"
AWARD_FIELDS = [
    "publication-number", "notice-title", "buyer-name", "buyer-country", "publication-date",
    "organisation-name-tenderer", "tender-value", "tender-value-cur",
    "received-submissions-type-val", "contract-duration-period-lot", "classification-cpv",
]
# Sample competitor file: cleaning contracts awarded by public buyers in Greater Copenhagen.
# Every row is taken from the TED contract award notice with the number shown.
# (notice, contract, buyer, supplier, value DKK, bids, published, term)
SAMPLE = [
    ("771876-2026", "Cleaning services", "Roskilde Universitet", "ProfilService A/S", 50501953, 5, "2026-11-06", ""),
    ("728482-2026", "Laboratory cleaning (re-tender)", "Fødevarestyrelsen", "ProfilService", 2835000, 5, "2026-10-21", "48 months"),
    ("679804-2026", "Cleaning", "KOMBIT A/S", "Toma Facility Danmark A/S", 6693115, 5, "2026-10-02", ""),
    ("602427-2026", "Cleaning of the Boulevard tunnel", "Banedanmark", "Dalgas A/S", 13019502, 3, "2026-09-01", "4 years"),
    ("567493-2026", "Cleaning and window cleaning (re-tender)", "Erhvervsakademi København", "Profil Service A/S", 17500000, 4, "2026-08-17", ""),
    ("429434-2026", "Cleaning services", "Gymnasiefællesskabet", "Renas Service ApS", 4056562, 4, "2026-06-24", ""),
    ("405491-2026", "Cleaning services", "Gymnasiefællesskabet", "Forenede Service A/S", 5818390, 5, "2026-06-12", ""),
    ("368964-2026", "Cleaning services", "HF & VUC Nordsjælland", "Renas Service ApS", 7132630, 8, "2026-05-29", ""),
    ("353067-2026", "Cleaning services", "Albertslund Kommune", "ProfilService A/S", 137124411, 6, "2026-05-22", ""),
    ("257899-2026", "Cleaning and stairwell cleaning", "Almenindkøb", "Servicefirmaet Eksakt Rengøring ApS", 5031975, 5, "2026-04-15", ""),
    ("206161-2026", "Office cleaning", "BIOFOS A/S", "Profil Service A/S", 22521800, 17, "2026-03-25", "96 months"),
    ("805982-2025", "Cleaning services", "Københavns Universitet", "Forenede Service A/S", 151890119, 6, "2025-12-04", ""),
    ("758806-2025", "Cleaning and canteen operation, Amager Hospital", "Region Hovedstaden", "Coor Service Management A/S", 117186160, 3, "2025-11-17", "5 years"),
    ("756146-2025", "Cleaning services", "Dansk Institut for Internationale Studier", "Toma Facility Danmark A/S", 2979720, 4, "2025-11-14", ""),
]


# ---------------------------------------------------------------- data
def ted_search(query: str, fields: list[str], max_pages: int = 40) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        body = json.dumps({"query": query, "fields": fields, "page": page, "limit": 250,
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


def fetch_notices(today: dt.date) -> list[dict]:
    since = today - dt.timedelta(days=DAYS - 1)
    iso3 = " ".join(c[2] for c in COUNTRIES)
    return ted_search(
        f"publication-date>={since:%Y%m%d} AND buyer-country IN ({iso3}) "
        f"AND notice-type IN ({OPEN_TYPES}) AND deadline-receipt-tender-date-lot>={today:%Y%m%d} "
        "SORT BY publication-date DESC", FIELDS)


def fetch_awards(today: dt.date) -> list[dict]:
    """Contract award notices of the last 30 days. The site still builds if this fails."""
    since = today - dt.timedelta(days=DAYS - 1)
    iso3 = " ".join(c[2] for c in COUNTRIES)
    try:
        return ted_search(
            f"publication-date>={since:%Y%m%d} AND buyer-country IN ({iso3}) "
            "AND notice-type IN (can-standard) SORT BY publication-date DESC", AWARD_FIELDS, 16)
    except Exception as exc:
        print(f"Award notices not loaded: {exc}", file=sys.stderr)
        return []


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


def shape_award(n: dict) -> dict | None:
    pub = n.get("publication-number")
    winners = uniq(pick_list(n.get("organisation-name-tenderer")))
    if not pub or not winners:
        return None
    values = []
    for v in n.get("tender-value") or []:
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            pass
    currencies = uniq(n.get("tender-value-cur"))
    bids = []
    for v in n.get("received-submissions-type-val") or []:
        try:
            bids.append(int(float(v)))
        except (TypeError, ValueError):
            pass
    terms = []
    for d in n.get("contract-duration-period-lot") or []:
        if isinstance(d, dict) and d.get("value") and d.get("unit"):
            unit = str(d["unit"]).lower()
            terms.append(f"{d['value']} {unit}{'' if str(d['value']) == '1' else 's'}")
    terms = list(dict.fromkeys(terms))
    title = pick(n.get("notice-title"))
    parts = [p.strip() for p in title.split(" – ")]
    own = " – ".join(parts[2:]) if len(parts) >= 3 else title
    category = parts[1] if len(parts) >= 3 else ""
    cpv = uniq(n.get("classification-cpv"))
    shown = "; ".join(winners[:3]) + (f" and {len(winners) - 3} more" if len(winners) > 3 else "")
    return {
        "id": pub,
        "t": own or title,
        "c": category,
        "b": pick(n.get("buyer-name")),
        "n": (uniq(n.get("buyer-country")) or [""])[0],
        "p": (uniq(n.get("publication-date")) or [""])[0][:10],
        "w": shown,
        "v": round(sum(values)) if values and len(currencies) == 1 else None,
        "u": currencies[0] if len(currencies) == 1 else "",
        "k": max(bids) if bids and max(bids) > 0 else None,
        "m": terms[0] if len(terms) == 1 else "",
        "s": sectors_for(cpv),
    }


def pick_list(value) -> list[str]:
    """All names from a multilingual TED field, in one language."""
    if isinstance(value, dict):
        for lang in ("eng", "dan", "swe", "nor", "fin"):
            if value.get(lang):
                return pick_list(value[lang])
        for v in value.values():
            if v:
                return pick_list(v)
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)] if value else []


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
.cta{border:1px solid var(--ink);background:var(--row);padding:16px 18px;margin:22px 0 30px;max-width:760px}
.cta h2{font:700 18px/1.3 Georgia,"Iowan Old Style","Times New Roman",serif;margin:0 0 6px}
.cta p{margin:0 0 12px}
.cta .note{margin:10px 0 0}
h2.sec{font:700 20px/1.3 Georgia,"Iowan Old Style","Times New Roman",serif;margin:0 0 6px}
.item.aw,.colhead.aw{grid-template-columns:1fr 230px 120px}
.win{font-size:14px}.win small{display:block;font-size:12px;color:var(--soft)}
.colhead.aw span:nth-child(2){text-align:left}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin:0 0 30px}
.cols h3{font:700 16px/1.3 Georgia,"Iowan Old Style","Times New Roman",serif;margin:0 0 4px}
.cols p{margin:0;color:var(--soft);font-size:14px}
.tw{overflow-x:auto;margin:0 0 12px}
table.file{border-collapse:collapse;width:100%;font-size:14px;min-width:640px}
table.file th{font-size:12px;color:var(--soft);text-transform:uppercase;letter-spacing:.6px;text-align:left;font-weight:400;padding:6px 10px 6px 0;border-bottom:2px solid var(--ink)}
table.file td{padding:9px 10px 9px 0;border-bottom:1px solid var(--rule);vertical-align:top}
table.file .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
h2.sec{margin-top:34px}
p.more a{font-weight:600}
footer{border-top:1px solid var(--rule);margin-top:44px;padding:18px 0 40px;font-size:13px;color:var(--soft)}
footer p{margin:0 0 6px;max-width:760px}
@media (max-width:700px){
 .item,.colhead{grid-template-columns:1fr auto}
 .colhead span:nth-child(3),.item .val{display:none}
 .item.aw,.colhead.aw{grid-template-columns:1fr}
 .colhead.aw{display:none}
 .item.aw .val{display:block;text-align:left}
 .cols{grid-template-columns:1fr}
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
(function(){
 var list=document.getElementById('awards'); if(!list) return;
 var q=document.getElementById('q'),fc=document.getElementById('fc'),fs=document.getElementById('fs'),so=document.getElementById('so');
 var cnt=document.getElementById('count'),more=document.getElementById('more');
 var data=null,shown=60,names=JSON.parse(list.getAttribute('data-countries'));
 function money(v,u){if(!v)return '';var s=v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?Math.round(v/1e3)+'k':String(v);return s+' '+(u||'');}
 function esc(s){return String(s||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
 function row(a){var bids=a.k?(a.k+(a.k===1?' bid':' bids')):'bids not stated';
  return '<li class="item aw"><div><a class="ttl" target="_blank" rel="noopener" href="https://ted.europa.eu/en/notice/-/detail/'+esc(a.id)+'">'+esc(a.t)+'</a>'+
  '<div class="meta">'+esc(a.b)+' &middot; '+esc(names[a.n]||a.n)+(a.c?' &middot; '+esc(a.c):'')+'</div></div>'+
  '<div class="win">'+esc(a.w)+'<small>'+esc(bids)+(a.m?' &middot; '+esc(a.m):'')+'</small></div>'+
  '<div class="val">'+(a.v?esc(money(a.v,a.u)):'<small>value not stated</small>')+'<small>'+esc(a.p)+'</small></div></li>';}
 function apply(){ if(!data) return;
  var text=(q.value||'').toLowerCase().trim(),c=fc.value,s=fs.value;
  var out=data.filter(function(a){
   if(c&&a.n!==c) return false; if(s&&a.s.indexOf(s)<0) return false;
   if(text&&(a.t+' '+a.b+' '+a.c+' '+a.w).toLowerCase().indexOf(text)<0) return false; return true;});
  var k=so.value;
  out.sort(function(a,b){ if(k==='value') return (b.v||0)-(a.v||0); if(k==='bids') return (b.k||0)-(a.k||0); return a.p<b.p?1:a.p>b.p?-1:0;});
  cnt.textContent=out.length+' contract award'+(out.length===1?'':'s');
  list.innerHTML=out.slice(0,shown).map(row).join('');
  more.hidden=out.length<=shown;
 }
 [q,fc,fs,so].forEach(function(el){el.addEventListener(el===q?'input':'change',function(){shown=60;apply();});});
 more.addEventListener('click',function(){shown+=60;apply();});
 fetch(list.getAttribute('data-src')).then(function(r){return r.json();}).then(function(j){data=j;apply();}).catch(function(){});
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


def award_row_html(a: dict) -> str:
    meta = f"{esc(a['b'])} &middot; {esc(COUNTRY_NAME.get(a['n'], a['n']))}" + (f" &middot; {esc(a['c'])}" if a["c"] else "")
    bids = f"{a['k']} bid{'' if a['k'] == 1 else 's'}" if a["k"] else "bids not stated"
    val = esc(money(a["v"], a["u"])) if a["v"] else "<small>value not stated</small>"
    return (f"<li class='item aw'><div><a class=ttl target=_blank rel=noopener "
            f"href='https://ted.europa.eu/en/notice/-/detail/{esc(a['id'])}'>{esc(a['t'])}</a>"
            f"<div class=meta>{meta}</div></div>"
            f"<div class=win>{esc(a['w'])}<small>{esc(bids)}{' &middot; ' + esc(a['m']) if a['m'] else ''}</small></div>"
            f"<div class=val>{val}<small>{esc(a['p'])}</small></div></li>")


def awards_listing(items: list[dict], today: dt.date, limit: int = SERVER_ROWS, interactive: bool = True) -> str:
    rows = "".join(award_row_html(a) for a in items[:limit])
    head = "<div class='colhead aw' aria-hidden=true><span>Contract</span><span>Awarded to</span><span>Value</span></div>"
    if not interactive:
        return head + f"<ol class=list>{rows}</ol>"
    countries = json.dumps({iso: name for _, name, iso, _ in COUNTRIES})
    copts = "".join(f"<option value='{iso}'>{name}</option>" for _, name, iso, _ in COUNTRIES)
    sopts = "".join(f"<option value='{slug}'>{name}</option>" for slug, name, _ in SECTORS)
    return (
        "<div class=filters role=search>"
        "<input id=q type=search placeholder='Search contract, buyer or supplier (any language)' aria-label='Search awards'>"
        f"<select id=fc aria-label='Country'><option value=''>All countries</option>{copts}</select>"
        f"<select id=fs aria-label='Sector'><option value=''>All sectors</option>{sopts}</select>"
        "<select id=so aria-label='Sort'><option value='new'>Newest first</option><option value='value'>Highest value</option>"
        "<option value='bids'>Most bids</option></select></div>"
        + f"<div class=count id=count>{len(items)} contract award{'' if len(items) == 1 else 's'}</div>"
        + head
        + f"<ol class=list id=awards data-src='awards.json' data-countries='{esc(countries)}'>{rows}</ol>"
        + f"<button class=more id=more{' hidden' if len(items) <= limit else ''}>Show more</button>"
    )


def sample_table(rows) -> str:
    body = "".join(
        f"<tr><td><b>{esc(buyer)}</b><br><span class=note>{esc(contract)}</span></td><td>{esc(supplier)}</td>"
        f"<td class=num>{value / 1e6:.1f}M DKK</td><td class=num>{bids}</td><td>{esc(term) or '<span class=note>not stated</span>'}</td>"
        f"<td><a target=_blank rel=noopener href='https://ted.europa.eu/en/notice/-/detail/{nid}'>{nid}</a><br><span class=note>{pub}</span></td></tr>"
        for nid, contract, buyer, supplier, value, bids, pub, term in rows)
    return ("<div class=tw><table class=file><thead><tr><th>Buyer and contract</th><th>Awarded to</th><th class=num>Award value</th>"
            "<th class=num>Bids</th><th>Term</th><th>TED notice</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def supplier_key(name: str) -> str:
    key = name.lower().replace(" ", "")
    for suffix in ("a/s", "aps"):
        key = key.removesuffix(suffix)
    return key


def page(title: str, desc: str, body: str, path: str, today: dt.date, active: str = "") -> str:
    canonical = f"{SITE_URL}/{path}" if path != "index.html" else f"{SITE_URL}/"
    nav = "".join(
        f"<a href='{href}'{' aria-current=page' if key == active else ''}>{label}</a>"
        for key, href, label in (("file", "competitor-file.html", "Competitor file"), ("awards", "awards.html", "Recent awards"),
                                 ("tenders", "tenders.html", "Open tenders"), ("pricing", "pricing.html", "Pricing"),
                                 ("about", "about.html", "About")))
    sub = "".join(f"<a href='{slug}.html'>{name}</a>" for slug, name, _, _ in COUNTRIES) + \
          "".join(f"<a href='{slug}.html'>{name}</a>" for slug, name, _ in SECTORS if slug in SUBNAV_SECTORS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:type" content="website">
<style>{CSS}</style></head><body>
<header class=mast><div class=w><a class=logo href="index.html">{BRAND}<small>Nordic public contract intelligence</small></a><nav>{nav}</nav></div></header>
<div class=sub><div class=w><span>Open tenders by country and sector:</span>{sub}</div></div>
<main class=w>{body}</main>
<footer><div class=w>
<p>Updated {today:%d %B %Y}. Notices come from TED, the EU's official journal for public procurement (&copy; European Union, reused under the Commission's open data policy). Read the official notice before you bid.</p>
<p>{BRAND}, Copenhagen, Denmark &middot; <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> &middot; {BRAND} is independent and is not part of the EU or any public authority.</p>
</div></footer>
<script>{JS}</script>
</body></html>"""


def build(notices: list[dict], out: Path, today: dt.date, award_notices: list[dict] | None = None) -> dict:
    seen, tenders = set(), []
    for t in (shape(n) for n in notices):
        if t and t["id"] not in seen:
            seen.add(t["id"])
            tenders.append(t)
    tenders.sort(key=lambda t: (t["p"], t["id"]), reverse=True)
    seen, awards = set(), []
    for a in (shape_award(n) for n in award_notices or []):
        if a and a["id"] not in seen:
            seen.add(a["id"])
            awards.append(a)
    awards.sort(key=lambda a: (a["p"], a["id"]), reverse=True)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):
        old.unlink()
    (out / "tenders.json").write_text(json.dumps(tenders, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (out / "awards.json").write_text(json.dumps(awards, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    pages = []

    def write(name, html_text):
        (out / name).write_text(html_text, encoding="utf-8")
        pages.append(name)

    week = sum(1 for t in tenders if t["p"] >= (today - dt.timedelta(days=6)).isoformat())
    mail_file = f"mailto:{CONTACT_EMAIL}?subject=Competitor%20file%20request"
    request_box = (
        f"<div class=cta><h2>Your first competitor file is free</h2>"
        f"<p>Send us the tender you are looking at (a TED notice number or a link is enough) or your trade and region. "
        f"You get the file by email within one working day.</p>"
        f"<a class=btn href='{mail_file}'>Request a free competitor file</a>"
        f"<p class=note>Or write to <a href='mailto:{CONTACT_EMAIL}'>{CONTACT_EMAIL}</a>.</p></div>")

    # ---- home
    with_value = sum(1 for a in awards if a["v"])
    awards_block = ""
    if awards:
        awards_block = (
            f"<h2 class=sec>Awarded in the last {DAYS} days</h2>"
            f"<p class=lede>{len(awards)} contract awards from Nordic public buyers name the winning supplier, "
            f"{with_value} of them with the award value. The newest are below.</p>"
            + awards_listing(awards, today, limit=8, interactive=False)
            + "<p class=more><a href='awards.html'>All recent awards</a></p>")
    home = (
        "<h1>Know who won the contract last time, at what price, against how many bids</h1>"
        f"<p class=lede>Before you price a public tender in the Nordics, {BRAND} gives you the competitor file: "
        "the previous awards by the same buyer and in the same trade, with the winning supplier, the award value, "
        "the number of bids and the contract term. Every line comes from an official contract award notice and carries its TED number.</p>"
        + request_box +
        "<div class=cols>"
        "<div><h3>What is in a file</h3><p>The buyer's earlier awards for the same kind of work, and awards by neighbouring buyers "
        "in your trade: who won, for how much, how many bids came in, and how long the contract runs where the notice states it.</p></div>"
        "<div><h3>When it helps</h3><p>When you decide whether to bid and what price to enter. You see who you are up against "
        "and what the buyer has paid before, while there is still time to act on it.</p></div>"
        "<div><h3>Where it comes from</h3><p>Contract award notices that public buyers must publish on TED. "
        "We do not estimate. If a notice leaves a figure out, the file says so.</p></div></div>"
        "<h2 class=sec>From a sample file</h2>"
        "<p class=lede>Cleaning contracts awarded by public buyers in Greater Copenhagen. Four of the fourteen lines in the "
        "<a href='competitor-file.html'>full sample</a>.</p>"
        + sample_table(SAMPLE[:4]) +
        "<h2 class=sec>Pricing</h2>"
        f"<div class=price><b>EUR {PRICE_FILE}</b> per competitor file. The first one is free.<br>"
        f"<b>EUR {PRICE_SUB}</b> per month for a standing brief on one trade in one region. The first month is free. "
        "<a href='pricing.html'>Details</a></div>"
        + awards_block +
        "<h2 class=sec>Open tenders today</h2>"
        f"<p class=lede>{len(tenders)} calls for tender from public buyers in Denmark, Sweden, Norway, Finland and Iceland still accept bids, "
        f"{week} of them published in the last seven days. <a href='tenders.html'>Search the open tenders</a></p>")
    write("index.html", page(f"Competitor files for Nordic public tenders | {BRAND}",
                             "Who won the public contract last time, at what price and against how many bids. "
                             "Competitor files for tenders in Denmark, Sweden, Norway, Finland and Iceland, built from TED award notices.",
                             home, "index.html", today))

    # ---- sample competitor file
    counts: dict[str, list] = {}
    for row in SAMPLE:
        entry = counts.setdefault(supplier_key(row[3]), [row[3], 0, 0])
        entry[1] += 1
        entry[2] += row[4]
    ranking = "".join(
        f"<tr><td>{esc(name)}</td><td class=num>{n}</td><td class=num>{total / 1e6:.1f}M DKK</td></tr>"
        for name, n, total in sorted(counts.values(), key=lambda e: (-e[1], -e[2])))
    sample = (
        "<h1>Sample competitor file</h1>"
        "<p class=lede>Public cleaning contracts in Greater Copenhagen. This is what we send: one page you can read before you price a bid. "
        f"The lines below are {len(SAMPLE)} contract award notices published on TED between {SAMPLE[-1][6]} and {SAMPLE[0][6]} "
        "in which the buyer states the award value.</p>"
        "<h2 class=sec>Contracts and who holds them</h2>"
        + sample_table(SAMPLE) +
        "<p class=note>Award value is the total stated in the notice for the whole contract period. "
        "Bids is the number of tenders received as stated in the notice. Term is shown only where the notice states it.</p>"
        "<h2 class=sec>Suppliers in this file</h2>"
        "<div class=tw><table class=file><thead><tr><th>Supplier</th><th class=num>Contracts won</th><th class=num>Total award value</th></tr></thead>"
        f"<tbody>{ranking}</tbody></table></div>"
        "<h2 class=sec>What a file for your tender adds</h2>"
        "<div class=prose><p>For a specific open tender we start from the buyer: its earlier awards for the same work, the supplier in place today "
        "and the value that contract was awarded at. Then we add the awards from comparable buyers nearby, so you can see which suppliers bid "
        "in the area and at what level.</p></div>"
        + request_box)
    write("competitor-file.html", page(f"Sample competitor file: public cleaning contracts in Copenhagen | {BRAND}",
                                       "A sample competitor file: who holds public cleaning contracts in Greater Copenhagen, the award values, "
                                       "the number of bids and the contract terms, from TED award notices.",
                                       sample, "competitor-file.html", today, "file"))

    # ---- recent awards
    body = (f"<h1>Public contracts awarded in the Nordics</h1>"
            f"<p class=lede>{len(awards)} contract award notices from the last {DAYS} days that name the winning supplier, "
            f"from public buyers in Denmark, Sweden, Norway, Finland and Iceland. Search by buyer, supplier or type of work. "
            f"For a contract split into lots, the value is the sum of the lots and the bid count is the highest lot figure.</p>"
            + awards_listing(awards, today)
            + request_box)
    write("awards.html", page(f"Recent public contract awards in the Nordics: who won | {BRAND}",
                              f"{len(awards)} public contracts awarded in Denmark, Sweden, Norway, Finland and Iceland in the last {DAYS} days, "
                              "with winning supplier, award value and number of bids. Updated every morning.",
                              body, "awards.html", today, "awards"))

    # ---- open tenders
    body = (f"<h1>Open public tenders in the Nordic countries</h1>"
            f"<p class=lede>{len(tenders)} calls for tender from public buyers in Denmark, Sweden, Norway, Finland and Iceland "
            f"that still accept bids. {week} of them were published in the last seven days. The list is rebuilt from TED every morning.</p>"
            "<p>By sector: " + ", ".join(f"<a href='{slug}.html'>{name}</a>" for slug, name, _ in SECTORS) + "</p>"
            + listing(tenders, today, {}))
    write("tenders.html", page(f"Open public tenders in the Nordics ({len(tenders)}) | {BRAND}",
                               f"{len(tenders)} open public tenders in Denmark, Sweden, Norway, Finland and Iceland from TED, "
                               "searchable by keyword, country, sector and deadline. Updated every morning.",
                               body, "tenders.html", today, "tenders"))

    for slug, name, iso, local in COUNTRIES:
        lst = [t for t in tenders if t["n"] == iso]
        body = (f"<h1>Open public tenders in {name}</h1>"
                f"<p class=lede>{len(lst)} calls for tender from public buyers in {name} ({local}) that still accept bids, "
                f"published on TED in the last {DAYS} days. Bidding on one of them? "
                f"<a href='competitor-file.html'>See who won it last time</a>.</p>" + listing(lst, today, {"c": iso}))
        write(f"{slug}.html", page(f"Public tenders in {name}: {len(lst)} open | {BRAND}",
                                   f"{len(lst)} open public tenders in {name} from TED, with buyer, deadline and value. Updated every morning.",
                                   body, f"{slug}.html", today, "tenders"))

    for slug, name, _ in SECTORS:
        lst = [t for t in tenders if slug in t["s"]]
        body = (f"<h1>{name}: open public tenders in the Nordics</h1>"
                f"<p class=lede>{len(lst)} open calls for tender in {name.lower()} from Nordic public buyers. "
                f"The sector is matched on the CPV codes the buyer chose, so check the notice for the exact scope. "
                f"Bidding on one of them? <a href='competitor-file.html'>See who won it last time</a>.</p>"
                + listing(lst, today, {"s": slug}))
        write(f"{slug}.html", page(f"{name} tenders in the Nordics: {len(lst)} open | {BRAND}",
                                   f"{len(lst)} open public tenders in {name.lower()} in Denmark, Sweden, Norway, Finland and Iceland. Updated every morning.",
                                   body, f"{slug}.html", today, "tenders"))

    # ---- pricing
    pricing = f"""<div class=prose>
<h1>Pricing</h1>
<p class=lede>Two ways to buy. Prices exclude VAT.</p>
<div class=price><b>Competitor file: EUR {PRICE_FILE}</b><br>One file for one tender or one trade and region: the buyer's earlier awards, the supplier in place, award values, number of bids and contract terms, each with its TED notice number. Delivered by email within one working day. Your first file is free.</div>
<div class=price><b>Standing brief: EUR {PRICE_SUB} per month</b><br>For one trade in one region. A full contract overview once a month and a short brief every Monday with the new awards and the new tenders in your area. The first month is free. Each further trade or region is EUR {PRICE_SUB} per month. Billed monthly, cancel any time.</div>
<p><a class=btn href="{mail_file}">Request a free competitor file</a></p>
<h2>What we need from you</h2>
<p>For a competitor file: the TED notice number or a link to the tender. For a standing brief: the kind of work you bid on and the regions you cover.</p>
<h2>What you should know</h2>
<p>Files are built from TED, which covers contracts above the EU thresholds. Smaller contracts that only appear on national portals are not included. Where a buyer left the value, the number of bids or the term out of its notice, the file says so. We do not fill gaps with estimates.</p>
<h2>Data access</h2>
<p>If you want the raw notices as a spreadsheet or an API feed, see <a href="alerts.html">alerts and API</a>.</p>
</div>"""
    write("pricing.html", page(f"Pricing | {BRAND}",
                               f"Competitor file EUR {PRICE_FILE}, first one free. Standing brief for one trade and region EUR {PRICE_SUB} per month, first month free.",
                               pricing, "pricing.html", today, "pricing"))

    alerts = f"""<div class=prose>
<h1>Alerts and API</h1>
<p class=lede>For teams that want the raw notices in their own tools: the tenders that match your business every morning, as a spreadsheet or an API feed, through our tender finder on Apify.</p>
<h2>What you set up once</h2>
<p>Keywords in any language (for example <i>rengøring</i>, <i>städning</i> or <i>cloud</i>), the countries you sell to, CPV codes if you use them, and a minimum contract value. Then add a daily schedule in Apify.</p>
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
<div class=price><b>$0.003 per tender delivered</b><br>No subscription. Runs that find nothing new cost close to nothing. Apify adds its own platform fee and has a free monthly allowance.</div>
<p><a class=btn href="{ACTOR_URL}">Open the tender finder on Apify</a></p>
<h2>Coverage</h2>
<p>All notices on TED, which covers contracts above the EU thresholds from every EU and EEA country. Smaller national tenders that only appear on national portals such as udbud.dk or Doffin are not included.</p>
<p class=note>Questions or a missing filter: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p>
</div>"""
    write("alerts.html", page(f"Tender alerts and API | {BRAND}",
                              "Daily alerts for new public tenders in the Nordics and the EU, by keyword, country and CPV code. $0.003 per tender, no subscription.",
                              alerts, "alerts.html", today))

    about = f"""<div class=prose>
<h1>About</h1>
<p>{BRAND} is a public contract intelligence service based in Copenhagen. We work with suppliers who bid for public contracts in Denmark, Sweden, Norway, Finland and Iceland.</p>
<p>Public buyers must publish their larger contracts, and the outcome of each one, on TED, the EU's official journal. The award notices say who won, at what value and how many suppliers bid. That information is public, but it sits in thousands of separate notices in several languages. We bring it together around the one decision a supplier has to make: whether to bid, and at what price.</p>
<h2>How we work</h2>
<p>Every figure in a competitor file is taken from an official notice and shown with its TED notice number, so you can check it yourself. We do not estimate values or contract end dates. Where a notice leaves something out, we say so.</p>
<h2>Where the data comes from</h2>
<p>The official TED search service of the Publications Office of the European Union. The site is rebuilt from it every morning. We shorten titles, use the English version where TED has one, and add sector labels based on the CPV codes the buyer chose.</p>
<h2>Contact</h2>
<p>{BRAND}, Copenhagen, Denmark<br><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
<p>We answer within one working day.</p>
</div>"""
    write("about.html", page(f"About | {BRAND}", f"{BRAND} is a public contract intelligence service in Copenhagen for suppliers bidding in the Nordic countries.",
                             about, "about.html", today, "about"))

    urls = "".join(f"<url><loc>{SITE_URL}/{p if p != 'index.html' else ''}</loc><lastmod>{today.isoformat()}</lastmod></url>"
                   for p in pages)
    (out / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "data.json").write_text(json.dumps({"updated": today.isoformat(), "count": len(tenders), "awards": len(awards),
                                               "by_country": {iso: sum(1 for t in tenders if t["n"] == iso)
                                                              for _, _, iso, _ in COUNTRIES}}), encoding="utf-8")
    return {"tenders": len(tenders), "awards": len(awards), "pages": len(pages)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture")
    ap.add_argument("--awards-fixture")
    ap.add_argument("--out", default="docs")
    ap.add_argument("--today")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    notices = json.loads(Path(args.fixture).read_text()) if args.fixture else fetch_notices(today)
    if args.awards_fixture:
        award_notices = json.loads(Path(args.awards_fixture).read_text())
    else:
        award_notices = [] if args.fixture else fetch_awards(today)
    stats = build(notices, Path(args.out), today, award_notices)
    print(f"Built {stats['pages']} pages with {stats['tenders']} open tenders and {stats['awards']} awards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
