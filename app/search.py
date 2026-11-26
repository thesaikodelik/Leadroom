from __future__ import annotations

import math
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from app import listings, market
from app.config import ScraperConfig
from app.filters import (
    domain_key,
    homepage_url,
    is_good_business_url,
    is_relevant_to_location,
    is_relevant_to_niche,
)
from app.search_providers import SearchProvider, create_provider


class SearchStopped(RuntimeError):
    pass


# Web queries per search pass. Each "search more" runs the next batch, so a market
# keeps finding new businesses instead of asking for pages the search engine
# no longer has.
QUERY_BATCH = 12
# List pages read per pass, and names from them looked up on the web.
LISTING_PAGES = 6
NAME_LOOKUPS = 10


def build_queries(niche: str, location: str, areas: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Every query for a market: its phrasings across the city, then district by district.

    "best ... in London" queries bring back list articles and directories, which are
    read for the businesses they name.
    """
    phrases = market.search_phrases(niche)
    typed = phrases[0]
    queries = [f"{typed} {location}", f'{typed} "{location}" contact', f"best {typed} in {location}"]
    for phrase in phrases[1:]:
        queries += [f"{phrase} {location}", f"best {phrase} in {location}"]
    for area in areas:
        for phrase in phrases[:2]:
            queries.append(f"{phrase} {area} {location}")
    return list(dict.fromkeys(queries))


def search_business_sites(
    config: ScraperConfig,
    provider: SearchProvider | None = None,
    excluded_domains: set[str] | None = None,
    diagnostics: dict[str, int | bool] | None = None,
    start_page: int = 0,
    local_start_page: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[], None] | None = None,
    deadline: float | None = None,
    pending_names: list[str] | None = None,
) -> list[dict[str, str]]:
    """Candidate businesses for a market from the web, list pages and the local map.

    Reaching the deadline ends the search early but keeps what was found; only a
    stop by the user discards it.
    """
    unique: list[dict[str, Any]] = []
    candidate_positions: dict[str, int] = {}
    seen_domains: set[str] = set()
    excluded_domains = excluded_domains or set()
    provider = provider or create_provider(config.search_provider, config.brave_search_api_key)
    areas = _areas(provider, config.location)
    queries = build_queries(config.niche, config.location, areas)
    batches = max(1, math.ceil(len(queries) / QUERY_BATCH))
    listing_pages: list[str] = []
    web_paths: dict[str, set[str]] = {}
    listing_count = 0
    listed_count = 0
    name_lookup_count = 0
    target_pool = (
        config.max_sites
        if provider.name == "osm_local"
        else min(500, max(config.max_sites * 2, config.max_results_per_query))
    )
    max_pages = 2 if excluded_domains else 1
    raw_result_count = 0
    relevant_result_count = 0
    previous_result_count = 0
    duplicate_result_count = 0
    successful_sources = 0
    failed_sources = 0
    local_result_count = 0
    web_result_count = 0
    merged_result_count = 0
    pages_searched = 0
    last_page = start_page - 1
    local_page = start_page if local_start_page is None else local_start_page

    def check_control() -> None:
        if cancel_check and cancel_check():
            raise SearchStopped("Search was stopped")

    def out_of_time() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    # Queries get at most a little over half of the time: the list pages and the
    # names on them, read afterwards, find the most businesses.
    query_deadline = None if deadline is None else time.monotonic() + (deadline - time.monotonic()) * 0.55

    def queries_out_of_time() -> bool:
        return out_of_time() or (query_deadline is not None and time.monotonic() >= query_deadline)

    def controlled_sleep(seconds: float) -> None:
        remaining = seconds
        while remaining > 0 and not out_of_time():
            check_control()
            interval = min(0.1, remaining)
            time.sleep(interval)
            remaining -= interval

    def note_listing(url: str, title: str, body: str) -> bool:
        """Remember a page about businesses to read later; True when the result is one."""
        if not listings.looks_like_listing(url, title, config.blocked_domains, config.niche, config.location):
            return False
        text = f"{url} {title} {body}"
        if (
            url not in listing_pages
            and market.narrowing_covered(config.niche, text)
            and _mentions_place(text, config.location, areas)
        ):
            listing_pages.append(url)
        return True

    def collect(item: dict[str, Any], listed_on: str = "") -> None:
        nonlocal relevant_result_count, previous_result_count, duplicate_result_count
        nonlocal local_result_count, web_result_count, merged_result_count
        url = item.get("url") or ""
        title = item.get("title", "")
        body = item.get("snippet", "")
        structured = item.get("source") == "osm_local"
        source_name = "local" if structured else "web"
        if structured:
            local_result_count += 1
        else:
            web_result_count += 1
        if not structured and not listed_on:
            # A directory or list article is read for the businesses it names; it is
            # not itself a lead.
            if note_listing(url, title, body) or not is_good_business_url(url, title, config.blocked_domains):
                return
            web_paths.setdefault(domain_key(url), set()).add(url.split("?", 1)[0].rstrip("/"))
            # The model's synonyms count too: "Persian supermarket" is an Iranian one.
            if not is_relevant_to_niche(url, title, body, config.niche) and market.missing_concepts(
                config.niche, f"{domain_key(url)} {title} {body}"
            ):
                return
            if not is_relevant_to_location(url, title, body, config.location) and not _mentions_place(
                f"{title} {body}", "", areas
            ):
                return
        elif listed_on and (
            not is_good_business_url(url, title, config.blocked_domains)
            or listings.looks_like_listing(url, title, config.blocked_domains, config.niche, config.location)
        ):
            return
        relevant_result_count += 1
        domain = item.get("domain") or domain_key(url)
        if domain in excluded_domains:
            previous_result_count += 1
            return
        if domain in candidate_positions:
            duplicate_result_count += 1
            position = candidate_positions[domain]
            before = set(unique[position].get("sources") or [])
            unique[position] = _merge_search_candidate(unique[position], dict(item), source_name)
            if len(set(unique[position].get("sources") or [])) > len(before):
                merged_result_count += 1
            return
        seen_domains.add(domain)
        if structured:
            candidate = dict(item)
        else:
            candidate = {
                "title": title,
                "url": url,
                "homepage": homepage_url(url),
                "snippet": body,
                "domain": domain,
                "source": "web",
            }
        candidate["sources"] = list(dict.fromkeys([*(candidate.get("sources") or []), source_name]))
        if listed_on:
            candidate["listed_on"] = listed_on
        candidate["source_evidence"] = [_search_evidence(candidate, source_name)]
        candidate_positions[domain] = len(unique)
        unique.append(candidate)

    executor: ThreadPoolExecutor | None = None
    local_future: Future[list[dict[str, str]]] | None = None
    try:
        market_search = getattr(provider, "search_market", None)
        if market_search:
            check_control()
            if progress_callback:
                progress_callback()
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-discovery")
            local_future = executor.submit(
                market_search,
                config.niche,
                config.location,
                target_pool,
                local_page * target_pool,
            )
            if provider.name == "osm_local":
                last_page = start_page

        page_range = [] if provider.name == "osm_local" else range(start_page, start_page + max_pages)
        for page in page_range:
            if queries_out_of_time():
                break
            last_page = page
            # Each pass runs the next batch of queries; once every batch has run, the
            # same queries are asked for their next page of results.
            batch = page % batches
            offset = (page // batches) * config.max_results_per_query
            for query in queries[batch * QUERY_BATCH : (batch + 1) * QUERY_BATCH]:
                if queries_out_of_time():
                    break
                check_control()
                if progress_callback:
                    progress_callback()
                print(f"\nSearch query [{provider.name}, page {page + 1}]: {query}")
                started = time.perf_counter()
                try:
                    results = provider.search(query, config.max_results_per_query, offset)
                except Exception as exc:
                    failed_sources += 1
                    print(f"Search failed [{provider.name}]: {type(exc).__name__}: {exc}")
                    continue
                successful_sources += 1
                check_control()
                pages_searched += 1
                raw_result_count += len(results)
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                print(f"Search result [{provider.name}]: {len(results)} result(s), {elapsed_ms} ms")

                for item in results:
                    collect(item)

                controlled_sleep(config.delay_seconds)
            if len(unique) >= target_pool:
                break

        # A site that came back with several different pages (a directory's page per
        # shop) is a directory: read those pages for the names, do not read it as a lead.
        directories = {domain for domain, paths in web_paths.items() if len(paths) >= 2}
        # Any page of a site that also gave a list page belongs to that directory.
        directories |= {domain_key(page) for page in listing_pages}
        if directories:
            for position in sorted(
                (
                    index
                    for index, item in enumerate(unique)
                    if item.get("domain") in directories
                    and item.get("sources") == ["web"]
                    and not item.get("listed_on")
                ),
                reverse=True,
            ):
                listing_pages.append(str(unique[position].get("url") or ""))
                del unique[position]
            candidate_positions.clear()
            candidate_positions.update({item["domain"]: index for index, item in enumerate(unique)})

        # Read the list pages the queries turned up for the businesses they name.
        names: list[str] = list(pending_names or [])
        for listing_url in listing_pages[:LISTING_PAGES]:
            if out_of_time():
                break
            check_control()
            if progress_callback:
                progress_callback()
            found = listings.harvest(listing_url, config.blocked_domains)
            listing_count += 1
            print(f"List page: {listing_url} ({len(found['links'])} link(s), {len(found['names'])} name(s))")
            for link in found["links"]:
                before = len(unique)
                collect({**link, "snippet": f"Listed on {domain_key(listing_url)}"}, listed_on=listing_url)
                listed_count += len(unique) - before
            names.extend(name for name in found["names"] if name not in names)

        # Names without a website link: look them up on the local map, then on the web.
        named = listings.rank_names(
            listings.lookup_names([name for name in names if not _named_candidate(name, unique)]),
            config.niche,
        )
        name_finder = getattr(provider, "find_names", None)
        if named and name_finder and not out_of_time():
            check_control()
            try:
                for item in name_finder(named[:30], config.location):
                    collect(item)
            except Exception as exc:  # the local map is optional for a web search
                print(f"Local name lookup failed: {type(exc).__name__}: {exc}")
        still_named = [name for name in named if not _named_candidate(name, unique)]
        if provider.name != "osm_local":
            for name in list(still_named[:NAME_LOOKUPS]):
                if out_of_time():
                    break
                still_named.remove(name)
                check_control()
                if progress_callback:
                    progress_callback()
                try:
                    results = provider.search(f'"{name}" {config.location}', 5, 0)
                except Exception as exc:
                    print(f"Name lookup failed for {name}: {type(exc).__name__}: {exc}")
                    continue
                name_lookup_count += 1
                for item in results:
                    text = f"{item.get('url', '')} {item.get('title', '')} {item.get('snippet', '')}"
                    # The business must be the named one, and in the searched place: a
                    # namesake abroad is not a lead.
                    if _names_business(name, item) and (
                        is_relevant_to_location(
                            str(item.get("url") or ""),
                            str(item.get("title") or ""),
                            str(item.get("snippet") or ""),
                            config.location,
                        )
                        or _mentions_place(text, "", areas)
                    ):
                        collect(dict(item), listed_on=str(item.get("url") or ""))
                        break
                controlled_sleep(config.delay_seconds)

        if local_future is not None:
            check_control()
            try:
                # The local map answers in seconds; give it a little time even when the web
                # search used up the deadline.
                timeout = None if deadline is None else max(10.0, deadline - time.monotonic())
                local_results = local_future.result(timeout=timeout)
                successful_sources += 1
            except FutureTimeout as exc:
                local_future.cancel()
                raise SearchStopped("Local discovery timed out") from exc
            except Exception as exc:
                failed_sources += 1
                print(f"Search failed [osm_local]: {type(exc).__name__}: {exc}")
                local_results = []
            pages_searched += 1
            raw_result_count += len(local_results)
            for item in local_results:
                collect(item)
    finally:
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        close = getattr(provider, "close", None)
        if close:
            close()

    if successful_sources == 0 and failed_sources:
        raise RuntimeError("All configured discovery sources failed")

    if diagnostics is not None:
        diagnostics.update(
            {
                "raw_results": raw_result_count,
                "relevant_results": relevant_result_count,
                "previously_seen_filtered": previous_result_count,
                "duplicates_filtered": duplicate_result_count,
                "local_results": local_result_count,
                "web_results": web_result_count,
                "merged_results": merged_result_count,
                "new_candidates": len(unique),
                "pages_searched": pages_searched,
                "next_search_page": last_page + 1,
                "next_local_page": local_page + 1 if local_future is not None else local_page,
                "target_reached": len(unique) >= config.max_sites,
                "districts": len(areas),
                "queries_total": len(queries),
                "list_pages_read": listing_count,
                "listed_businesses": listed_count,
                "name_lookups": name_lookup_count,
                # Names not looked up yet; the next "search more" starts with them.
                "pending_names": still_named[:80],
            }
        )

    unique.sort(
        key=lambda item: (
            len(item.get("sources") or []),
            bool(item.get("email") or item.get("phone")),
            bool(item.get("url")),
        ),
        reverse=True,
    )
    return unique


def _areas(provider: SearchProvider, location: str) -> list[str]:
    """The districts of a location, when the provider has the local map."""
    finder = getattr(provider, "areas", None)
    if not finder:
        return []
    try:
        return list(finder(location))
    except Exception as exc:  # districts only widen the search
        print(f"Districts unavailable: {type(exc).__name__}: {exc}")
        return []


def _mentions_place(text: str, location: str, areas: list[str]) -> bool:
    text = text.casefold()
    places = [*(location.casefold().replace(",", " ").split()[:1]), *(area.casefold() for area in areas)]
    return any(place and place in text for place in places)


def _name_words(name: str) -> list[str]:
    return [word for word in market.market_words(name) if len(word) >= 3]


def _names_business(name: str, item: dict[str, Any]) -> bool:
    """Whether a search result is the named business itself, not a page that mentions it."""
    words = _name_words(name)
    text = f"{domain_key(str(item.get('url') or ''))} {item.get('title', '')}".casefold()
    return bool(words) and all(word in text for word in words)


def _named_candidate(name: str, candidates: list[dict[str, Any]]) -> bool:
    words = _name_words(name)
    return bool(words) and any(
        all(word in f"{item.get('title', '')} {item.get('domain', '')}".casefold() for word in words)
        for item in candidates
    )


def _search_evidence(candidate: dict[str, Any], source: str) -> dict[str, str]:
    return {
        "source": source,
        "url": str(candidate.get("listed_on") or candidate.get("osm_url") or candidate.get("url") or ""),
        "source_id": str(candidate.get("source_id") or candidate.get("domain") or ""),
    }


def _merge_search_candidate(current: dict[str, Any], incoming: dict[str, Any], source: str) -> dict[str, Any]:
    merged = dict(current)
    current_sources = list(current.get("sources") or [])
    incoming_sources = list(incoming.get("sources") or [source])
    merged["sources"] = list(dict.fromkeys([*current_sources, *incoming_sources]))
    evidence = [*(current.get("source_evidence") or []), _search_evidence(incoming, source)]
    evidence_by_location = {f"{item.get('source')}:{item.get('url')}": item for item in evidence}
    merged["source_evidence"] = list(evidence_by_location.values())
    for field in (
        "business_name",
        "business_type",
        "city_or_area",
        "address",
        "phone",
        "email",
        "latitude",
        "longitude",
        "osm_url",
        "source_id",
    ):
        if incoming.get(field) and not merged.get(field):
            merged[field] = incoming[field]
    for field in ("url", "homepage", "title"):
        if incoming.get(field) and not merged.get(field):
            merged[field] = incoming[field]
    snippets = [value for value in (current.get("snippet"), incoming.get("snippet")) if value]
    merged["snippet"] = " | ".join(dict.fromkeys(snippets))
    merged["source"] = "hybrid" if len(merged["sources"]) > 1 else current.get("source", source)
    return merged
