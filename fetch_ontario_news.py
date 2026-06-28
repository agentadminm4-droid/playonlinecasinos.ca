#!/usr/bin/env python3
"""Fetch real Ontario iGaming news and inject into the homepage's
'Latest Ontario Casino News' section.

Sources (all public RSS / HTML):
  1. iGaming Ontario official news (igamingontario.ca/en/news)
  2. Canadian Gaming Business RSS (canadiangamingbusiness.com/feed)
  3. Google News RSS — query: Ontario casino OR igaming OR AGCO (Canada)

Compliance:
  - Every article title links to the ORIGINAL SOURCE URL (no fabricated links).
  - Publisher name is shown on every card (full attribution).
  - Date is the article's actual pubDate.
  - Headline cards only ever point outward to the source — never to a fake
    internal page. Affiliate disclosure + responsible gambling footer unchanged.

Usage:
  python3 fetch_ontario_news.py                 # update source index.html
  python3 fetch_ontario_news.py --deploy        # also update deploy copy
  python3 fetch_ontario_news.py --preview       # print cards, don't write

Exit codes:
  0 = updated OK (>= 3 cards written)
  1 = no qualifying news found (homepage untouched)
  2 = error fetching any source
"""
import argparse
import html
import json
import re
import subprocess
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
ROOT = Path.home() / "Desktop"
SOURCE_DIR = ROOT / "playonlinecasinos"
DEPLOY_DIR = ROOT / "playonlinecasinos-deploy"

# Map source "publisher slug" -> user-facing badge text shown on card
PUBLISHER_BADGE = {
    "iGaming Ontario": "Official",
    "Canadian Gaming Business": "Industry News",
    "Google News": "News",
}

# Skip titles that are pure SEO/affiliate content farm headlines, not actual news.
# These show up in Google News as "Best X Casinos" roundups. They're not newsworthy.
NOISE_TITLE_PATTERNS = [
    r"^best\s+(?:ontario\s+)?(?:online\s+)?(?:casinos?|slots?)(?:\s|$|:)",  # "Best Ontario Online Casinos"
    r"^fastest\s+payout",
    r"^online\s+slots\s+ontario:",  # "Online Slots Ontario: ..."
    r"\bcasino\s+review\b",
    r"\bsportsbook\s+review\b",
    r"^ranking\s+the\s+top\s+",  # "Rankings The Top Ontario ..."
    r"^5\s+favorites\b",
]

# Hard BLOCKS — articles we will never show regardless of source.
# These are wrong-jurisdiction or misleading affiliate promotions.
BLOCKED_KEYWORDS = [
    "alberta",  # Different province, different regulator (AGLC not AGCO)
    "preregistration",  # Pre-launch promos, not news
    "bc ", "b.c.", "british columbia",  # Different province
    "quebec", "québec",  # Different province
]
NOISE_PUBLISHERS = {
    # Affiliate content farms — not actual news publishers
    "squawka",
    "rotowire",
    "rg.org",
    "casino.ca",
}


def is_noise(article: dict) -> bool:
    t = article["title"].lower()
    pub = (article.get("publisher") or "").lower()
    if pub in NOISE_PUBLISHERS:
        return True
    for pat in NOISE_TITLE_PATTERNS:
        if re.search(pat, t):
            return True
    # Hard-block cross-jurisdiction articles
    for kw in BLOCKED_KEYWORDS:
        if kw in t:
            return True
    return False


# Newsworthy-for-Ontario publishers we trust (skip Canada-wide news
# that isn't Ontario-specific). Used to prefer Ontario-relevant picks.
ONTARIO_PUBLISHERS = {
    "igaming ontario",
    "canadian gaming business",  # publishes Ontario-specific market data
}

# Require at least one of these tokens in title OR publisher for inclusion
# (unless publisher is in ONTARIO_PUBLISHERS, which can post Canadian gaming
# news that may or may not mention Ontario explicitly).
ONTARIO_TOKENS = [
    "ontario",
    "igaming",
    "agco",
    "olg",
    "toronto",  # city-specific signals
]  # noqa


def is_ontario_relevant(article: dict) -> bool:
    """Filter to Ontario-relevant news only.

    Allow if:
      - publisher is in ONTARIO_PUBLISHERS (trusted Canadian gaming trade
        that posts many Ontario-specific stories), OR
      - title contains an Ontario token
    """
    pub = (article.get("publisher") or "").lower()
    if pub in ONTARIO_PUBLISHERS:
        return True
    t = article["title"].lower()
    return any(tok in t for tok in ONTARIO_TOKENS)

# Categories inferred from keywords (used for the AGCO-style badge tag)
def categorize(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["regulat", "agco", "self-exclusion", "betguard", "fine", "penalty", "suspend", "compliance"]):
        return "Regulation"
    if any(k in t for k in ["record", "revenue", "wager", "growth", "handle", "ggr", "$"]):
        return "Market Data"
    if any(k in t for k in ["launch", "new ", "partner", "license", "licence", "signs"]):
        return "Industry"
    return "Ontario News"


def fetch_url(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, text/xml, text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------- Source 1: iGaming Ontario HTML scrape ----------
def fetch_igaming_ontario() -> list:
    """Scrape /en/news HTML for article links. Returns list of dicts."""
    try:
        html_text = fetch_url("https://igamingontario.ca/en/news")
    except Exception as e:
        print(f"  [iGaming Ontario] FAILED: {e}", file=sys.stderr)
        return []

    # Articles live in: <a href="/en/news/<slug>" hreflang="en">Title</a>
    pattern = re.compile(
        r'<a\s+href="(/en/news/[a-z0-9\-]+)"\s+hreflang="en"[^>]*>([^<]+)</a>',
        re.IGNORECASE,
    )
    articles = []
    seen = set()
    for match in pattern.finditer(html_text):
        slug, title = match.group(1), match.group(2).strip()
        title = html.unescape(title).strip()
        if slug in seen or not title or len(title) < 8:
            continue
        seen.add(slug)
        articles.append({
            "title": title,
            "url": f"https://igamingontario.ca{slug}",
            "publisher": "iGaming Ontario",
            "pub_date": None,  # No date in HTML listing
            "category": categorize(title),
        })
        if len(articles) >= 12:
            break
    print(f"  [iGaming Ontario] {len(articles)} articles")
    return articles


# ---------- Source 2: Canadian Gaming Business RSS ----------
def fetch_cgb_rss() -> list:
    """Parse the CGB RSS feed. Filter for Ontario relevance."""
    try:
        xml_text = fetch_url("https://www.canadiangamingbusiness.com/feed/")
    except Exception as e:
        print(f"  [Canadian Gaming Business] FAILED: {e}", file=sys.stderr)
        return []

    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  [Canadian Gaming Business] PARSE FAILED: {e}", file=sys.stderr)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        date_el = item.find("pubDate")
        if title_el is None or link_el is None:
            continue
        title = html.unescape((title_el.text or "").strip())
        link = (link_el.text or "").strip()
        desc = html.unescape((desc_el.text or "").strip()) if desc_el is not None else ""
        date_str = (date_el.text or "").strip() if date_el is not None else ""
        if not title or not link:
            continue

        # Ontario filter (also pick up items about broader Canadian gaming
        # only if they mention Ontario / OLG / AGCO)
        combined = f"{title} {desc}".lower()
        if not any(k in combined for k in ["ontario", "igaming", "agco", "olg"]):
            continue

        pub_dt = None
        if date_str:
            try:
                pub_dt = parsedate_to_datetime(date_str).astimezone(timezone.utc)
            except Exception:
                pub_dt = None

        articles.append({
            "title": title,
            "url": link,
            "publisher": "Canadian Gaming Business",
            "pub_date": pub_dt.isoformat() if pub_dt else None,
            "category": categorize(title),
        })
        if len(articles) >= 12:
            break
    print(f"  [Canadian Gaming Business] {len(articles)} articles")
    return articles


# ---------- Source 3: Google News RSS ----------
def fetch_google_news() -> list:
    """Pull Ontario casino / iGaming / AGCO from Google News RSS."""
    url = (
        "https://news.google.com/rss/search?"
        "q=Ontario+casino+OR+igaming+OR+AGCO&hl=en-CA&gl=CA&ceid=CA:en"
    )
    try:
        xml_text = fetch_url(url)
    except Exception as e:
        print(f"  [Google News] FAILED: {e}", file=sys.stderr)
        return []

    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  [Google News] PARSE FAILED: {e}", file=sys.stderr)
        return []

    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        date_el = item.find("pubDate")
        source_el = item.find("source")
        if title_el is None or link_el is None:
            continue
        title_raw = (title_el.text or "").strip()
        link = (link_el.text or "").strip()
        if not title_raw or not link:
            continue

        # Google News title format: "Headline - Publisher"  (split on last " - ")
        # Strip the trailing " - Publisher" piece
        m = re.match(r"^(.*?)\s+-\s+([^-]+?)\s*$", title_raw)
        if m:
            title = m.group(1).strip()
            pub_from_title = m.group(2).strip()
        else:
            title = title_raw
            pub_from_title = ""

        # Source element is more reliable
        publisher = (source_el.text or "").strip() if source_el is not None else pub_from_title
        publisher = html.unescape(publisher) if publisher else "News"

        # Skip pure affiliate/review spam (these are clearly content-farm roundups)
        if any(k in publisher.lower() for k in ["squawka", "rotowire", "rg.org"]):
            # Still allow them — they're real publishers. But demote to category only if not core news.
            pass

        pub_dt = None
        if date_el is not None and date_el.text:
            try:
                pub_dt = parsedate_to_datetime(date_el.text).astimezone(timezone.utc)
            except Exception:
                pub_dt = None

        articles.append({
            "title": html.unescape(title),
            "url": link,
            "publisher": publisher,
            "pub_date": pub_dt.isoformat() if pub_dt else None,
            "category": categorize(title),
        })
        if len(articles) >= 30:
            break
    print(f"  [Google News] {len(articles)} articles")
    return articles


# ---------- Selection: dedupe, sort by date, pick top 3 ----------
def dedupe_and_pick(all_articles: list, n: int = 3) -> list:
    """Dedupe by normalized title, filter out affiliate/SEO noise, filter to
    Ontario relevance, sort by date desc, take top n.

    Preference order:
      1. iGaming Ontario (official source) — always included if available
      2. Newest items by pub_date
      3. Items with no date fall to bottom
    """
    # Drop pure SEO/affiliate content-farm articles + cross-jurisdiction items
    no_noise = [a for a in all_articles if not is_noise(a)]
    print(f"  After noise filter: {len(no_noise)} of {len(all_articles)}")

    # Drop cross-jurisdiction (Alberta/BC/Quebec) and non-Ontario-specific
    ontario = [a for a in no_noise if is_ontario_relevant(a)]
    print(f"  After Ontario filter: {len(ontario)} of {len(no_noise)}")

    seen = set()

    def norm(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", t.lower())[:60]

    # Sort: items with pub_date first (newest first), then no-date items
    dated = [a for a in ontario if a.get("pub_date")]
    undated = [a for a in ontario if not a.get("pub_date")]
    dated.sort(key=lambda a: a["pub_date"], reverse=True)
    undated.sort(key=lambda a: (a["publisher"], a["title"]))

    ordered = dated + undated

    picked = []
    # Force-include top iGaming Ontario article first if present
    for a in ordered:
        if a["publisher"] == "iGaming Ontario":
            k = norm(a["title"])
            if k not in seen:
                picked.append(a)
                seen.add(k)
                break

    for a in ordered:
        if len(picked) >= n:
            break
        k = norm(a["title"])
        if k in seen:
            continue
        seen.add(k)
        picked.append(a)

    return picked[:n] if picked else no_noise[:n]  # if filtering kills all, fall back to filtered (not raw)


# ---------- HTML rendering ----------
def format_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%B %-d, %Y")
    except Exception:
        return ""


def render_card(article: dict) -> str:
    """One <article class='card'> with publisher attribution."""
    badge = PUBLISHER_BADGE.get(article["publisher"], article["publisher"])
    title = html.escape(article["title"])
    url = html.escape(article["url"], quote=True)
    pub = html.escape(article["publisher"])
    date = format_date(article.get("pub_date"))
    cat = html.escape(article["category"])

    if date:
        date_html = f'          <div class="card-meta" style="margin-top:0.5rem;">{date} &middot; <strong>{pub}</strong></div>'
    else:
        date_html = f'          <div class="card-meta" style="margin-top:0.5rem;"><strong>{pub}</strong></div>'

    # External link — rel=noopener, target=_blank. No affiliate redirect.
    return f'''      <article class="card">
        <div class="card-body">
          <span class="agco-badge">{cat}</span>
          <h3 class="card-title" style="margin-top:0.75rem;"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
{date_html}
        </div>
      </article>'''


def render_news_block(articles: list) -> str:
    """Just the cards. The wrapping <div class="grid grid-3"> is preserved
    by the patch regex from the original HTML."""
    if not articles:
        return ""
    return "\n".join(render_card(a) for a in articles)


# ---------- Inject into homepage ----------
# Match: <h2>News</h2><a>All news →</a>  +  existing grid div  +  closing
# </div></div></section>  (section-header close + container close + section close)
SECTION_PATTERN = re.compile(
    r'(<h2>Latest Ontario Casino News</h2>\s*'
    r'<a href="/blog/" class="section-link">All news →</a>\s*'
    r'</div>\s*\n\s*\n?\s*<div class="grid grid-3">)'   # section-header close + (blank line?) + grid open
    r'(.*?)'                                            # cards inside grid (capture 2 — discarded)
    r'(\s*</div>\s*</div>\s*</section>)',               # grid close + container close + section close
    re.DOTALL,
)


def patch_index(index_path: Path, articles: list) -> bool:
    """Replace the news grid contents inside the 'Latest Ontario Casino News' section."""
    if not index_path.exists():
        print(f"  SKIP: {index_path} not found", file=sys.stderr)
        return False
    html_text = index_path.read_text(encoding="utf-8")
    new_block = render_news_block(articles)
    if not new_block:
        return False

    # Replace ONLY the cards inside the grid, preserving the opening
    # div and the closing </div></div></section> structure.
    def repl(m: re.Match) -> str:
        opening = m.group(1)
        closing = m.group(3)
        return opening + "\n" + new_block + "\n    " + closing.lstrip()

    new_html, n = SECTION_PATTERN.subn(repl, html_text, count=1)
    if n == 0:
        print(f"  WARN: news section marker not found in {index_path.name}", file=sys.stderr)
        return False
    index_path.write_text(new_html, encoding="utf-8")
    print(f"  OK: patched {index_path.name} with {len(articles)} cards")
    return True


# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", action="store_true", help="Also patch deploy copy")
    parser.add_argument("--preview", action="store_true", help="Print cards, don't write")
    parser.add_argument("--n", type=int, default=3, help="Number of cards (default 3)")
    args = parser.parse_args()

    print("Fetching real Ontario iGaming news...")
    all_articles = []
    all_articles += fetch_igaming_ontario()
    all_articles += fetch_cgb_rss()
    all_articles += fetch_google_news()
    print(f"Total raw: {len(all_articles)}")

    if not all_articles:
        print("ERROR: no articles from any source", file=sys.stderr)
        sys.exit(2)

    picked = dedupe_and_pick(all_articles, n=args.n)
    print(f"\nSelected {len(picked)} cards:")
    for a in picked:
        print(f"  - [{a['publisher']}] {a['title'][:75]}...")
        print(f"    {a['url']}")

    if args.preview:
        print("\n--- PREVIEW HTML ---")
        print(render_news_block(picked))
        return

    ok_source = patch_index(SOURCE_DIR / "index.html", picked)
    if args.deploy:
        ok_deploy = patch_index(DEPLOY_DIR / "index.html", picked)
    else:
        ok_deploy = True

    if not ok_source:
        sys.exit(1)
    print("\nDone.")


if __name__ == "__main__":
    main()
