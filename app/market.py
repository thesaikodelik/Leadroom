"""What a run's market means, in words the system can check on its own.

A market such as "Iranian supermarket" is a set of concepts that must all hold for a
business to fit. Each concept is matched by the start of a word ("iran" finds
"Iranian" and "Iran"), widened by synonyms the local model suggests ("Persian"),
and checked twice: when candidates are searched, and again once a site is read.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.config import MODEL_CONTEXT_TOKENS

logger = logging.getLogger(__name__)

# Words that describe how a business is run or listed, not what it is.
QUALIFIERS = {
    "and",
    "business",
    "businesses",
    "company",
    "companies",
    "contractor",
    "contractors",
    "for",
    "in",
    "independent",
    "local",
    "near",
    "of",
    "provider",
    "providers",
    "service",
    "services",
    "shop",
    "shops",
    "store",
    "stores",
    "the",
}
# Endings that change a word's form but not its meaning, longest first. A nationality
# loses its ending so it also finds the country ("Iranian" -> "iran").
_NATIONAL_ENDINGS = ("ians", "ian", "eans", "ean", "ese", "ish")
_ENDINGS = (
    ("ians", ""),
    ("ian", ""),
    ("eans", "e"),
    ("ean", "e"),
    ("ese", ""),
    ("ish", ""),
    ("ies", "y"),
    ("ery", "er"),
    ("ers", "er"),
    ("es", "e"),
    ("s", ""),
)
_SYNONYM_TIMEOUT = 20.0
_synonyms: dict[str, dict[str, list[str]]] = {}
_synonyms_lock = threading.Lock()


def stem(word: str) -> str:
    word = word.casefold()
    for ending, replacement in _ENDINGS:
        # A plain plural may leave a short word ("pubs" -> "pub"); other endings
        # need a longer root so "bakery" or "korean" are not cut too far.
        shortest = 3 if ending == "s" else 4
        if word.endswith(ending) and not word.endswith("ss") and len(word) - len(ending) >= shortest:
            return word[: len(word) - len(ending)] + replacement
    return word


def market_words(niche: str) -> list[str]:
    """The words of a market that say what the business is, in the order written."""
    words = re.findall(r"[^\W_]+", niche.casefold())
    return list(dict.fromkeys(word for word in words if word not in QUALIFIERS and len(word) >= 2))


def _key(niche: str) -> str:
    return " ".join(market_words(niche))


def forms(word: str) -> list[str]:
    """How a word may start in a business's text.

    A form ending in "$" must be a whole word: "Iranian" also finds the country
    "Iran", but its short root must not find "Iranshahr" or, for "Persian",
    "personal".
    """
    word = " ".join(word.casefold().split())
    root = stem(word)
    if root == word:
        return [word]
    if word.endswith(_NATIONAL_ENDINGS):
        return [word, f"{root}$"]
    return [root]


def concepts(niche: str) -> list[tuple[str, ...]]:
    """One group of word forms per concept; a business must match every group."""
    known = _synonyms.get(_key(niche), {})
    groups: list[tuple[str, ...]] = []
    for word in market_words(niche):
        options = [*forms(word), *(form for option in known.get(word, []) for form in forms(option))]
        groups.append(tuple(dict.fromkeys(option for option in options if option.strip("$"))))
    return groups


def concept_pattern(group: tuple[str, ...]) -> str:
    """A regular expression for one concept; it works in Python and PostgreSQL alike."""
    options = [
        re.escape(option[:-1]) + "(?![a-z0-9])" if option.endswith("$") else re.escape(option)
        for option in group
    ]
    return r"(?:^|[^a-z0-9])(?:" + "|".join(options) + ")"


def covers(group: tuple[str, ...], text: str) -> bool:
    return re.search(concept_pattern(group), text.casefold()) is not None


def missing_concepts(niche: str, text: str) -> list[str]:
    """The market's words that the text never mentions, in any of their forms."""
    return [
        word
        for word, group in zip(market_words(niche), concepts(niche), strict=True)
        if not covers(group, text)
    ]


def prepare(config: Any) -> None:
    """Ask the local model once per market for other words a fitting business would use.

    Without a model the market keeps its own words; nothing else changes.
    """
    key = _key(config.niche)
    if not key or getattr(config, "ai_extraction", "auto") == "off":
        return
    with _synonyms_lock:
        if key in _synonyms:
            return
    words = market_words(config.niche)
    prompt = (
        f'Market: "{config.niche}".\n'
        "For each word below, give words that mean exactly the same thing and that a business "
        "in this market could use instead in its name or on its website. Give at most four, "
        "and an empty list when there are none.\n"
        "Only exact equivalents: another name for the same nationality or the same kind of "
        "business, or the country of a nationality. Never a wider region, a religion, a "
        "neighbouring nationality, or a related but different thing.\n"
        'Good: "iranian" -> ["persian", "iran"]; "barber" -> ["barbershop"]; '
        '"supermarket" -> ["grocery", "grocer", "minimarket"].\n'
        'Bad: "iranian" -> ["middle eastern", "islamic"]; "vegan" -> ["vegetarian"].\n'
        f"Words: {json.dumps(words)}\n"
        'Answer only with JSON shaped like {"word": ["equivalent"]}.'
    )
    answer = _ask_model(config, prompt)
    if answer is None:
        return
    found: dict[str, list[str]] = {}
    for word in words:
        options = answer.get(word) if isinstance(answer, dict) else None
        if not isinstance(options, list):
            continue
        clean = [
            " ".join(str(option).casefold().split())
            for option in options
            if isinstance(option, str) and re.fullmatch(r"[^\W\d_]+(?: [^\W\d_]+){0,2}", option.strip())
        ]
        found[word] = [option for option in dict.fromkeys(clean) if len(option) >= 3][:5]
    with _synonyms_lock:
        _synonyms[key] = found
    logger.info("Market %r widened with %s", config.niche, found)


def _ask_model(config: Any, prompt: str) -> Any | None:
    """One short JSON answer from the run's local Ollama model, or None when it cannot answer."""
    provider = config.model.split("/", 1)[0] if "/" in config.model else "ollama"
    if provider != "ollama":
        return None
    from app.scraper import local_model_problem  # imported here: the scraper imports this module

    if local_model_problem(config):
        return None
    try:
        response = httpx.post(
            f"{config.ollama_base_url}/api/chat",
            json={
                "model": config.model.removeprefix("ollama/"),
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                # The same context size as reading sites, so Ollama does not reload the model.
                "options": {"temperature": 0, "num_ctx": MODEL_CONTEXT_TOKENS},
            },
            timeout=_SYNONYM_TIMEOUT,
        )
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
    except Exception as exc:  # synonyms are a bonus; the market's own words still work
        logger.info("Market synonyms unavailable for %r: %s", config.niche, exc)
        return None


def page_text(html: str, limit: int = 40_000) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    parts = [soup.title.get_text(" ") if soup.title else ""]
    for meta in soup.find_all("meta"):
        if str(meta.get("name") or meta.get("property") or "").casefold() in {
            "description",
            "keywords",
            "og:title",
            "og:description",
        }:
            parts.append(str(meta.get("content") or ""))
    parts.append(soup.get_text(" "))
    return " ".join(" ".join(parts).split())[:limit]


def judge(lead: dict[str, Any], html: str, config: Any) -> dict[str, Any]:
    """Record whether the business that was read fits the market it was found for.

    A market is a kind of business (its last word: "supermarket") narrowed by the
    words before it ("Iranian"). The narrowing words must show on the site, in
    their own forms or as a synonym the model gave for this market: a site about
    supermarkets that never says anything Iranian is off the market. The
    kind of business is named in many ways ("grocery", "food store"), so a site
    that never uses the word is kept but marked unclear rather than set aside.
    """
    niche = config.niche
    words = market_words(niche)
    if not words:
        return lead
    text = " ".join(
        [
            str(lead.get("business_name") or ""),
            str(lead.get("business_type") or ""),
            " ".join(str(item) for item in lead.get("services") or []),
            page_text(html),
        ]
    )
    missing = missing_concepts(niche, text)
    narrowing = [word for word in missing if word != words[-1]]
    if not missing:
        lead["market_fit"] = "match"
        lead["market_fit_reason"] = ""
    elif narrowing:
        lead["market_fit"] = "off_market"
        lead["market_fit_reason"] = "The site never mentions " + " or ".join(narrowing) + "."
    else:
        lead["market_fit"] = "unclear"
        lead["market_fit_reason"] = (
            f"The site does not use the word {words[-1]}; check it is the right kind of business."
        )
    return lead


def search_phrases(niche: str, limit: int = 4) -> list[str]:
    """The market as typed, then the same market in the words the model gave.

    "Iranian supermarket" also becomes "Persian supermarket" and "Iranian grocery":
    one word swapped at a time, so each phrase still means the whole market.
    """
    typed = " ".join(niche.split())
    phrases = [typed]
    known = _synonyms.get(_key(niche), {})
    words = market_words(niche)
    for index, word in enumerate(words):
        for option in known.get(word, []):
            if stem(option) == stem(word) or option in words:
                continue
            phrases.append(" ".join([*words[:index], option, *words[index + 1 :]]))
    return list(dict.fromkeys(phrases))[:limit]


def narrowing_covered(niche: str, text: str) -> bool:
    """Whether a text names what narrows the market (the kind of business for a one-word market)."""
    words = market_words(niche)
    if not words:
        return True
    missing = set(missing_concepts(niche, text))
    needed = words[:-1] or words
    return not missing.intersection(needed)
