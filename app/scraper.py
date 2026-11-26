from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from pydantic import ValidationError
from scrapegraphai.graphs import SmartScraperGraph
from scrapegraphai.telemetry import disable_telemetry

from app.config import MODEL_CONTEXT_TOKENS, ScraperConfig
from app.enrichment import HtmlFetcher, apply_enrichment, enrich_public_pages
from app.filters import same_business_domain
from app.models import LeadExtraction
from app.normalizer import normalize_lead
from app.parser import parse_model_output

# ScrapeGraphAI otherwise uploads each page's URL, content, prompt and model
# response to its telemetry service. Its SCRAPEGRAPHAI_TELEMETRY_ENABLED variable
# is not honoured, so switch it off explicitly. Leadroom keeps that data local.
disable_telemetry()

logger = logging.getLogger(__name__)

# How long a finding that the local model is unreachable is trusted, so a run on a
# computer without Ollama does not wait on it for every site.
MODEL_CHECK_TTL = 60.0
_model_checks: dict[tuple[str, str], tuple[float, str]] = {}
_model_checks_lock = threading.Lock()

LEAD_PROMPT = """
Extract public B2B lead information from this small business website.

Return only valid JSON. Do not use markdown. Do not explain anything.

Use this exact structure:
{
  "is_valid_lead": true,
  "business_name": "",
  "website": "",
  "city_or_area": "",
  "business_type": "",
  "services": [],
  "generic_email": "",
  "emails": [],
  "phone": "",
  "phones": [],
  "contact_page": "",
  "booking_page": "",
  "instagram_or_social": "",
  "has_online_booking": false,
  "website_quality_note": ""
}

Rules:
- This must be a real individual business website. Freelancers, sole traders,
  studios, and personal brands offering paid services are valid businesses.
- Reject directories, marketplaces, booking platforms, review websites,
  large department stores, blog posts, and generic category pages.
- Use only public business information visible on the website.
- Prefer role addresses like info@, hello@, contact@, bookings@, studio@, or sales@.
- Also include a named address when the website publicly presents it as a business contact.
- Never guess a private address, and reject no-reply addresses or addresses from unrelated domains.
- Return up to three unique public business emails in emails and up to three public phone numbers in phones.
- Keep generic_email and phone equal to the first item in their matching list.
- Do not guess missing information.
- If a field is missing, keep it empty.
"""


def scrape_business_site(
    url: str,
    config: ScraperConfig,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    public_data, field_evidence, enrichment_errors = enrich_public_pages(
        url,
        config,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    if cancel_check and cancel_check():
        raise InterruptedError("Enrichment stopped")
    public_data = dict(public_data)
    field_evidence = dict(field_evidence)
    named_site = public_data.pop("site_name", "")
    named_site_evidence = field_evidence.pop("site_name", None)
    if named_site and not public_data.get("business_name"):
        # No JSON-LD name: use the name the home page gives itself. The model may
        # still name the business, but this name has a source page to show for it.
        public_data["business_name"] = named_site
        if named_site_evidence:
            field_evidence["business_name"] = named_site_evidence

    def without_model(reason: str) -> dict[str, Any]:
        # The rule-based pass already read the contact details, JSON-LD and pages;
        # keep those instead of failing the site.
        lead = normalize_lead({}, source_url=url)
        lead["ai_extraction"] = "skipped"
        lead["ai_skipped_reason"] = reason
        return apply_enrichment(lead, public_data, field_evidence, enrichment_errors)

    provider = config.model.split("/", 1)[0] if "/" in config.model else "ollama"
    llm_config: dict[str, Any] = {
        "model": config.model,
        "temperature": 0,
        "model_tokens": MODEL_CONTEXT_TOKENS,
    }
    if config.ollama_base_url:
        llm_config["base_url"] = config.ollama_base_url
    if provider == "ollama":
        llm_config["format"] = LeadExtraction.model_json_schema()
        llm_config["num_ctx"] = MODEL_CONTEXT_TOKENS
    elif config.llm_api_key:
        llm_config["api_key"] = config.llm_api_key
    graph_config = {
        "llm": llm_config,
        "verbose": False,
        "headless": True,
    }

    source_fetcher = HtmlFetcher(
        cache_dir=config.cache_dir,
        timeout_seconds=config.request_timeout_seconds,
        retry_attempts=config.retry_attempts,
        cache_ttl_hours=config.cache_ttl_hours,
        browser_fallback=config.browser_fallback,
        advanced_fetching=config.advanced_fetching,
    )
    try:
        guarded_page = source_fetcher.fetch(url)
        if not same_business_domain(guarded_page.url, url):
            raise ValueError("Website redirected to an unrelated domain")
        guarded_html = guarded_page.html
    finally:
        source_fetcher.close()

    if config.ai_extraction == "off":
        return without_model("AI extraction is off for this run.")
    unavailable = local_model_problem(config)
    if unavailable:
        return without_model(unavailable)
    graph = SmartScraperGraph(prompt=LEAD_PROMPT, source=guarded_html, config=graph_config)
    try:
        raw = _run_with_timeout(graph.run, config.ai_timeout_seconds, cancel_check)
    except InterruptedError:
        raise
    except TimeoutError:
        return without_model(
            f"The model took longer than {config.ai_timeout_seconds:.0f} seconds on this site."
        )
    except Exception as exc:  # the model, not the site, failed: keep what was found
        logger.warning("AI extraction failed for %s: %s", url, exc)
        forget_model_check(config)
        return without_model(f"The model could not read this site: {str(exc)[:300]}")
    parsed, raw_text = parse_model_output(raw)
    if isinstance(parsed, dict):
        try:
            parsed = LeadExtraction.model_validate(parsed).model_dump(exclude_none=True)
        except ValidationError as exc:
            lead = normalize_lead(None, source_url=url)
            lead["raw_output"] = raw_text
            lead["validation_errors"] = exc.errors(include_url=False)
            return apply_enrichment(lead, public_data, field_evidence, enrichment_errors)
    lead = normalize_lead(parsed, source_url=url)
    if not parsed:
        lead["raw_output"] = raw_text
    return apply_enrichment(lead, public_data, field_evidence, enrichment_errors)


def _run_with_timeout(
    work: Callable[[], Any],
    timeout: float,
    cancel_check: Callable[[], bool] | None = None,
) -> Any:
    """Run work in a daemon thread; give up after timeout or when the run is cancelled.

    A model call cannot be interrupted, so on timeout the thread is left to finish on
    its own and its answer is dropped.
    """
    outcome: dict[str, Any] = {}

    def target() -> None:
        try:
            outcome["value"] = work()
        except BaseException as exc:  # handed to the caller below
            outcome["error"] = exc

    thread = threading.Thread(target=target, name="ai-extraction", daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while thread.is_alive():
        if cancel_check and cancel_check():
            raise InterruptedError("Enrichment stopped")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"no answer within {timeout:.0f} seconds")
        thread.join(min(0.5, remaining))
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def _model_key(config: ScraperConfig) -> tuple[str, str]:
    return (config.ollama_base_url, config.model)


def forget_model_check(config: ScraperConfig) -> None:
    with _model_checks_lock:
        _model_checks.pop(_model_key(config), None)


def local_model_problem(config: ScraperConfig) -> str:
    """Why the local Ollama model cannot be used now, or "" when it can.

    Hosted providers are not checked here; a failing call falls back per site.
    """
    provider = config.model.split("/", 1)[0] if "/" in config.model else "ollama"
    if provider != "ollama":
        return ""
    key = _model_key(config)
    now = time.monotonic()
    with _model_checks_lock:
        cached = _model_checks.get(key)
        if cached and now - cached[0] < MODEL_CHECK_TTL:
            return cached[1]
    wanted = config.model.removeprefix("ollama/")
    try:
        response = httpx.get(f"{config.ollama_base_url}/api/tags", timeout=4)
        response.raise_for_status()
        names = {str(item.get("name", "")) for item in response.json().get("models", [])}
        if wanted in names or f"{wanted}:latest" in names:
            problem = ""
        else:
            problem = f"The model {wanted} is not installed in Ollama."
    except Exception:
        problem = "Ollama is not running, so sites were read without AI."
    with _model_checks_lock:
        _model_checks[key] = (now, problem)
    return problem
