"""Businesses named on list pages: directories and "best ... in London" articles.

A web search for a market returns many such pages. They are not leads, but each
names businesses of the market and often links to their own websites, so they
are read for those links and names instead of being thrown away.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.filters import domain_key, homepage_url, is_good_business_url

logger = logging.getLogger(__name__)

# Sites whose pages are about people or posts, not lists of businesses with websites.
SOCIAL_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "pinterest.com",
    "wikipedia.org",
}
# Titles of pages that list several businesses.
LIST_TITLE = re.compile(
    r"\b(?:best|top\s*\d*|\d+\s+(?:best|great)|list|directory|guide|where to (?:buy|find|eat|shop)|near me)\b",
    re.IGNORECASE,
)
# Headings that label a part of the page rather than name a business.
_HEADING_NOISE = re.compile(
    r"\b(?:best|top|where|how|why|what|guide|list|faq|frequently|our|you|your|near me|about|"
    r"contact|address|location|hours|opening|social|media|reviews?|rating|photos?|map|menu|"
    r"related|similar|nearby|share|comments?|newsletter|subscribe|cookies?|privacy|terms|"
    r"categor(?:y|ies)|popular|recent|latest|upcoming|events?|classifieds|browse|download|app|"
    r"posts?|details|information|overview|description|services|products|search|results|"
    r"login|sign|questions)\b",
    re.IGNORECASE,
)
# Links that lead to a tool or a page builder rather than a business.
_LINK_NOISE = re.compile(
    r"\b(?:powered by|optimi[sz]ed by|designed by|built with|cookie|privacy|terms|google play|app store)\b",
    re.IGNORECASE,
)
_TOOL_DOMAINS = {"wa.me", "t.me", "whatsapp.com", "goo.gl", "bit.ly", "apple.com", "play.google.com"}
_NUMBERING = re.compile(r"^\s*(?:no\.?\s*)?\d+\s*[.)\-:]?\s*")
_MAX_BYTES = 2_000_000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


# Paths of a directory's pages, whether they list many businesses or describe one.
DIRECTORY_PATH = re.compile(
    r"/(?:directory|directories|listings?|company|companies|places?|biz|business(?:es)?|"
    r"category|categories|search|find|stores?-near|near-me|blog|news|articles?|guides?)(?:/|$|-)"
    # A dated path is an article: /2024/08/23/...
    r"|/(?:19|20)\d{2}/\d{1,2}/",
    re.IGNORECASE,
)
# Titles that name a place rather than a business: "Iranian Supermarket in London".


def looks_like_listing(
    url: str,
    title: str,
    blocked_domains: set[str] | frozenset[str] = frozenset(),
    niche: str = "",
    location: str = "",
) -> bool:
    """Whether a result is a page about businesses (a list, directory or article) rather than one
    business's own website."""
    domain = domain_key(url)
    if not domain or domain in SOCIAL_DOMAINS:
        return False
    path = urlparse(url).path.casefold()
    city = next(iter(re.findall(r"[^\W\d_]+", location.casefold())), "")
    return (
        bool(LIST_TITLE.search(title))
        or bool(DIRECTORY_PATH.search(path))
        # A page filed under the city (/london/iranian-supermarket/) belongs to a site
        # about many places.
        or bool(city and re.search(rf"/{re.escape(city)}(?:/|$|-)", path))
        or _names_the_kind_in_plural(title, niche)
        or _titled_by_the_market(title, niche, city)
        or not is_good_business_url(url, title, blocked_domains)
    )


def _titled_by_the_market(title: str, niche: str, city: str) -> bool:
    """A page titled "Iranian Grocery Stores in London" is about the market in a city; a
    business puts its own name first ("ASA Market - Persian grocery in London")."""
    from app import market

    first = re.split(r"\s+[|:\-\u2013\u2014]\s+|\s*\|", title, maxsplit=1)[0].strip()
    words = market.market_words(niche)
    if (
        not city
        or not first
        or not words
        or not re.search(rf"\b(?:in|near)\s+{re.escape(city)}\b", first, re.IGNORECASE)
    ):
        return False
    first_word = first.split()[0]
    return any(market.covers(group, first_word) for group in market.concepts(niche)[: max(1, len(words) - 1)])


def _names_the_kind_in_plural(title: str, niche: str) -> bool:
    """ "Persian Supermarkets" is about several businesses; "Sahar Supermarket" is one."""
    from app import market

    words = market.market_words(niche)
    if not words:
        return False
    head = words[-1]
    plurals = {head + "s", head + "es", head[:-1] + "ies" if head.endswith("y") else head + "s"}
    return any(re.search(rf"\b{re.escape(plural)}\b", title, re.IGNORECASE) for plural in plurals)


def fetch_page(url: str, timeout: float = 8.0) -> str:
    """The HTML of a page, or "" when it cannot be read."""
    try:
        with (
            httpx.Client(
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"},
            ) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code >= 400 or "html" not in response.headers.get("content-type", ""):
                return ""
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > _MAX_BYTES:
                    break
            return body.decode(response.encoding or "utf-8", errors="replace")
    except Exception as exc:  # a list page that cannot be read only means fewer names
        logger.info("List page %s could not be read: %s", url, exc)
        return ""


def harvest(
    url: str,
    blocked_domains: set[str] | frozenset[str] = frozenset(),
    html: str | None = None,
    link_limit: int = 40,
    name_limit: int = 40,
) -> dict[str, Any]:
    """The businesses a list page links to, and the business names in its headings."""
    html = fetch_page(url) if html is None else html
    if not html:
        return {"links": [], "names": []}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        tag.decompose()
    page_domain = domain_key(url)
    links: dict[str, dict[str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(url, str(anchor["href"]).strip())
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        domain = domain_key(href)
        if not domain or domain == page_domain or domain in links or domain in SOCIAL_DOMAINS | _TOOL_DOMAINS:
            continue
        text = " ".join(anchor.get_text(" ").split())[:120]
        if _LINK_NOISE.search(text) or not is_good_business_url(href, text, blocked_domains):
            continue
        if len(text) < 3 or text.casefold() in _GENERIC_LINK_TEXT:
            heading = anchor.find_previous(["h2", "h3", "h4"])
            text = _business_name(heading.get_text(" ")) if heading else ""
        links[domain] = {
            "title": text or domain,
            "url": href,
            "homepage": homepage_url(href),
        }
        if len(links) >= link_limit:
            break
    names: list[str] = []
    # h1 names the business on a directory's page for one business; h2-h4 name the
    # entries of a list article.
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        name = _business_name(heading.get_text(" "))
        if name and name not in names:
            names.append(name)
        if len(names) >= name_limit:
            break
    for link in links.values():
        name = _business_name(link["title"])
        if name and name not in names:
            names.append(name)
    return {"links": list(links.values()), "names": names[: name_limit * 2]}


_GENERIC_LINK_TEXT = {"website", "visit website", "visit", "web", "site", "homepage", "read more", "more"}
# Latin and another script in one heading ("Aran Supermarket سوپرمارکت آران"): the Latin part names it
# the way web pages and the map do.
_LATIN_RUN = re.compile(r"[A-Za-z0-9&'.\- ]+")


def _business_name(text: str) -> str:
    """A heading such as "3. Super Sahar - Kensington" as a business name, or ""."""
    text = _NUMBERING.sub("", " ".join(text.split()))
    latin = max(_LATIN_RUN.findall(text), key=len, default="").strip()
    if (
        latin
        and re.search(r"[^\x00-\x7f]", text)
        and len(latin.split()) >= 1
        and any(c.isalpha() for c in latin)
    ):
        text = latin
    text = re.split(r"\s+[-–—|:,]\s+|\s*\(", text, maxsplit=1)[0].strip(" .:-")
    words = text.split()
    if not 1 <= len(words) <= 6 or len(text) < 4 or _HEADING_NOISE.search(text):
        return ""
    if not any(character.isalpha() for character in text) or text.casefold() in {
        "website",
        "visit website",
        "read more",
    }:
        return ""
    # A web address used as a link's text, or a word with emoji or symbols, is not a name.
    if re.fullmatch(r"[\w-]+(?:\.[\w-]+)+", text) or not re.fullmatch(r"[\w&'.\- ]+", text):
        return ""
    # "Supermarkets in Manchester" names a page, not a business; a long name with a
    # number ("Saffron 1 Mesghal 4.6g") is a product.
    if re.search(r"\b(?:in|near|more)\b", text, re.IGNORECASE):
        return ""
    if re.search(r"\d", text) and len(text.split()) > 2 or len(text.split()) > 4:
        return ""
    return text


def lookup_names(names: list[str]) -> list[str]:
    """Names worth looking up: one word ("Bakery", "Verisure") is too often a heading or an
    advert to find the right business by."""
    return [name for name in names if len(re.findall(r"[^\W\d_]{2,}", name)) >= 2]


def rank_names(names: list[str], niche: str) -> list[str]:
    """Names that carry a word of the market ("Bahar Supermarket") first: they are most
    likely to be businesses of the market rather than other entries on the page."""
    from app import market

    def score(name: str) -> int:
        lowered = name.casefold()
        return sum(market.covers(group, lowered) for group in market.concepts(niche))

    return sorted(dict.fromkeys(names), key=lambda name: (-score(name), names.index(name)))
