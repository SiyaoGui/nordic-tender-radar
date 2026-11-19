# Nordic Tender Radar

Website listing every open public tender in Denmark, Sweden, Norway, Finland and Iceland, rebuilt every morning from TED (the official EU procurement journal).

- `site/build.py` fetches open calls for tender from the TED Search API and writes static pages into `docs/`.
- `.github/workflows/site.yaml` runs it daily and publishes through GitHub Pages.
- Daily alerts and full exports: [EU Public Tender Finder on Apify](https://apify.com/nordic-tender-radar/eu-tender-finder).

Data: © European Union, ted.europa.eu, reused under the Commission's open data policy.
