"""Insights: data articles for the Tendernord website.

Each article is fixed at the time of writing. Every table row is taken from the TED
contract award notice with the number shown. build.py imports this module and writes
the pages returned by pages().
"""
from __future__ import annotations

import html

TED = "https://ted.europa.eu/en/notice/-/detail/"

# (notice, published, country, buyer, contract, awarded to, value, bids, term)
CLEANING_NOV_2026 = [
    ("819771-2026", "2026-11-25", "Denmark", "Boliggården, Helsingør", "Stairwell cleaning", "Anders Andersen's Rengøring A/S", "30.0M DKK", "up to 5", "4 years"),
    ("818016-2026", "2026-11-25", "Finland", "City of Helsinki, Culture and Leisure Division", "Cleaning services", "RTK-Palvelu Oy; Siskon Siivous Oy; Real Clean Finland Oy; SOL Palvelut Oy; IC Siivous Oy", "1.2M EUR", "11", "12 months"),
    ("815146-2026", "2026-11-24", "Denmark", "Copenhagen Business School", "Window cleaning", "QWC ApS", "4.8M DKK", "6", ""),
    ("807418-2026", "2026-11-20", "Norway", "Domstoladministrasjonen", "Cleaning, Asker and Bærum District Court", "4Service Eir Renhold AS", "4.7M NOK", "up to 3", "72 months"),
    ("807405-2026", "2026-11-20", "Norway", "Domstoladministrasjonen", "Cleaning, Søndre Østfold District Court", "4Service Eir Renhold AS", "8.4M NOK", "up to 3", "72 months"),
    ("807166-2026", "2026-11-19", "Sweden", "Domstolsverket", "Cleaning, Gothenburg District Court", "Northclean Facility Services AB", "10.8M SEK", "4", ""),
    ("806179-2026", "2026-11-19", "Sweden", "Norrköpings kommun", "Cleaning services, Navestad", "Östgöta Elitstäd AB", "12.0M SEK", "5", ""),
    ("805257-2026", "2026-11-19", "Finland", "City of Helsinki, Culture and Leisure Division", "Cleaning, Oodi Central Library", "N-Clean Oy", "1.45M EUR", "14", ""),
    ("803119-2026", "2026-11-18", "Finland", "Poliisiammattikorkeakoulu (Police University College)", "Cleaning services", "ISS Palvelut Oy", "2.6M EUR", "7", ""),
    ("794915-2026", "2026-11-16", "Sweden", "Vetlanda kommun", "Window cleaning", "Städ och fönsterputs dags i väst Sverige AB; PutsMan Aktiebolag", "4.5M SEK", "up to 6", ""),
    ("784214-2026", "2026-11-11", "Norway", "Domstoladministrasjonen", "Cleaning, Romerike and Glåmdal District Court", "4Service Eir Renhold AS; RAIDON AS", "9.5M NOK", "up to 5", "72 months"),
    ("783368-2026", "2026-11-11", "Sweden", "Simrishamns Bostäder AB", "Cleaning framework agreement", "Mariedal; iClean by Schön AB; Ultra Clean i Malmö Aktiebolag; Catch Me AB", "", "up to 5", ""),
    ("777048-2026", "2026-11-09", "Finland", "City of Espoo", "Cleaning, Leppävaara and Tapiola areas", "ISS Palvelut Oy; SOL Palvelut Oy; Alltime Suomi Oy", "17.3M EUR", "up to 9", ""),
    ("774584-2026", "2026-11-06", "Finland", "HSY Helsinki Region Environmental Services", "Cleaning for waste management sites", "Siskon Siivous Oy; Coor Service Management Oy", "1.53M EUR", "up to 9", ""),
    ("772368-2026", "2026-11-06", "Sweden", "Region Norrbotten", "Cleaning, Luleå", "Samhall Aktiebolag; Coor Service Management AB", "48.5M SEK", "up to 5", ""),
    ("771876-2026", "2026-11-06", "Denmark", "Roskilde Universitet", "Cleaning services", "ProfilService A/S", "50.5M DKK", "5", ""),
    ("751105-2026", "2026-10-29", "Sweden", "Örebrobostäder Aktiebolag", "Cleaning of stairwells, premises and flats", "NanoClean World AB; Nytorget Clean & Facility AB; QLNR i Örebro AB; TS Lokalvård Aktiebolag", "30.0M SEK", "6", ""),
]

ARTICLES = [
    {
        "slug": "insights-cleaning-awards-november-2026",
        "date": "27 November 2026",
        "title": "Who won public cleaning contracts in the Nordics, November 2026",
        "desc": "17 public cleaning contracts awarded in Sweden, Finland, Denmark and Norway in November 2026: "
                "the winning suppliers, award values and number of bids, each with its TED notice.",
        "lede": "Nordic public buyers published 17 contract award notices for building and window cleaning on TED "
                "between 29 October and 25 November 2026. Each is listed here with the winning suppliers, "
                "the value the buyer reported and the number of bids.",
        "intro": ["Six of the 17 notices come from Sweden, five from Finland, three from Denmark and three from Norway. "
                  "No buyer in Iceland published a cleaning award in the period."],
        "rows": CLEANING_NOV_2026,
        "note": "Value is the total the buyer reports in the notice. For a contract split into lots, "
                "bids is the highest lot figure. Term is shown only where the notice states it.",
        "sections": [
            ("The largest awards", [
                "In Denmark, Roskilde Universitet awarded its cleaning contract to ProfilService A/S at 50.5M DKK after five bids. "
                "In Sweden, Region Norrbotten awarded cleaning in Luleå to Samhall Aktiebolag and Coor Service Management AB, "
                "with a notice value of 48.5M SEK. In Finland, the City of Espoo awarded cleaning for the Leppävaara and Tapiola areas "
                "to ISS Palvelut Oy, SOL Palvelut Oy and Alltime Suomi Oy at 17.3M EUR. All three Norwegian notices come from "
                "Domstoladministrasjonen, the courts administration. The largest of them, for Romerike and Glåmdal District Court, is 9.5M NOK."]),
            ("Suppliers named more than once", [
                "4Service Eir Renhold AS is a winner in all three Norwegian notices. Each is for a district court and runs 72 months. "
                "In Finland, three suppliers appear twice: Siskon Siivous Oy (Helsinki's Culture and Leisure Division, and HSY), "
                "ISS Palvelut Oy (the Police University College and Espoo) and SOL Palvelut Oy (Helsinki and Espoo)."]),
            ("Bids and contract terms", [
                "Every notice states how many bids came in. The highest count is 14, for the cleaning of Oodi Central Library in Helsinki, "
                "which N-Clean Oy won at 1.45M EUR. Helsinki's Culture and Leisure Division received 11 bids for its cleaning services contract. "
                "The lowest count is three, for two of the Norwegian court contracts. Five of the 17 notices state a contract term."]),
            ("What the list covers", [
                "Contract award notices classified under CPV group 9091 (cleaning services) that name a winner. "
                "We left out notices under the same code for other work: damage restoration, sewer flushing, chimney sweeping, "
                "floor refurbishment and cleaning products. TED covers contracts above the EU thresholds, "
                "so smaller contracts published only on national portals are not included."]),
        ],
    },
]


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def table(rows) -> str:
    body = "".join(
        f"<tr><td><b>{esc(buyer)}</b><br><span class=note>{esc(contract)} &middot; {esc(country)}</span></td><td>{esc(winner)}</td>"
        f"<td class=num>{esc(value) or '<span class=note>not stated</span>'}</td><td class=num>{esc(bids)}</td>"
        f"<td>{esc(term) or '<span class=note>not stated</span>'}</td>"
        f"<td><a target=_blank rel=noopener style='white-space:nowrap' href='{TED}{nid}'>{nid}</a><br><span class=note>{pub}</span></td></tr>"
        for nid, pub, country, buyer, contract, winner, value, bids, term in rows)
    return ("<div class=tw><table class=file><thead><tr><th>Buyer and contract</th><th>Awarded to</th><th class=num>Value</th>"
            "<th class=num>Bids</th><th>Term</th><th>TED notice</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def article_body(a: dict) -> str:
    paras = lambda ps: "".join(f"<p>{esc(p)}</p>" for p in ps)
    sections = "".join(f"<h2>{esc(h)}</h2>{paras(ps)}" for h, ps in a["sections"])
    return (f"<p class=note style='margin:26px 0 -18px'><a href='insights.html'>Insights</a> &middot; {esc(a['date'])}</p>"
            f"<h1>{esc(a['title'])}</h1><p class=lede>{esc(a['lede'])}</p>"
            f"<div class=prose>{paras(a['intro'])}</div>"
            + table(a["rows"]) +
            f"<p class=note>{esc(a['note'])}</p>"
            f"<div class=prose>{sections}"
            "<p>The last 30 days of awards in every trade are in <a href='awards.html'>recent awards</a>.</p></div>")


def index_body() -> str:
    items = "".join(
        f"<li class=item style='grid-template-columns:1fr'><div><a class=ttl href='{a['slug']}.html'>{esc(a['title'])}</a>"
        f"<div class=meta>{esc(a['date'])} &middot; {esc(a['desc'])}</div></div></li>"
        for a in ARTICLES)
    return ("<h1>Insights</h1>"
            "<p class=lede>Short reports on who wins public contracts in the Nordic countries, built from contract award notices on TED. "
            "A new one every Friday.</p>"
            f"<ol class=list>{items}</ol>")


def pages(brand: str) -> list[tuple[str, str, str, str]]:
    """(file name, title, description, body html) for the index and every article."""
    out = [("insights.html", f"Insights: who wins public contracts in the Nordics | {brand}",
            "Weekly reports on public contract awards in Denmark, Sweden, Norway, Finland and Iceland, built from TED award notices.",
            index_body())]
    for a in ARTICLES:
        out.append((f"{a['slug']}.html", f"{a['title']} | {brand}", a["desc"], article_body(a)))
    return out
