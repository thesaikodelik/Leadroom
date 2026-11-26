import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import ScraperConfig
from app.database import RunRepository
from app.pipeline import run_pipeline
from app.scraper import scrape_business_site


class ScraperPipelineTests(unittest.TestCase):
    def setUp(self):
        # Tests must not depend on whether Ollama runs on this computer.
        model_check = patch("app.scraper.local_model_problem", return_value="")
        model_check.start()
        self.addCleanup(model_check.stop)

    def _fetcher(self, fetcher_class, url):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        fetcher_class.return_value.fetch.return_value.url = url

    @patch("app.scraper.enrich_public_pages")
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_ai_off_keeps_rule_based_details_without_calling_the_model(
        self, graph_class, fetcher_class, enrich
    ):
        self._fetcher(fetcher_class, "https://salon.example/")
        enrich.return_value = (
            {"business_name": "Rule Salon", "generic_email": "info@salon.example", "emails": ["info@salon.example"]},
            {
                "business_name": {"value": "Rule Salon", "source_url": "https://salon.example/", "method": "json-ld"},
                "generic_email": {"value": "info@salon.example", "source_url": "https://salon.example/contact", "method": "mailto"},
            },
            [],
        )
        config = ScraperConfig(niche="salons", location="London", ai_extraction="off")

        lead = scrape_business_site("https://salon.example/", config)

        graph_class.assert_not_called()
        self.assertEqual(lead["ai_extraction"], "skipped")
        self.assertEqual(lead["business_name"], "Rule Salon")
        self.assertIn("info@salon.example", lead["emails"])
        self.assertTrue(lead["is_valid_lead"])

    @patch("app.scraper.enrich_public_pages", return_value=({"phone": "+44 20 7946 0000"}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_missing_ollama_falls_back_instead_of_failing(self, graph_class, fetcher_class, _enrich):
        self._fetcher(fetcher_class, "https://salon.example/")
        config = ScraperConfig(niche="salons", location="London")
        with patch("app.scraper.local_model_problem", return_value="Ollama is not running."):
            lead = scrape_business_site("https://salon.example/", config)

        graph_class.assert_not_called()
        self.assertEqual(lead["ai_skipped_reason"], "Ollama is not running.")
        self.assertEqual(lead["phone"], "+44 20 7946 0000")

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_model_error_falls_back_for_that_site(self, graph_class, fetcher_class, _enrich):
        self._fetcher(fetcher_class, "https://salon.example/")
        graph_class.return_value.run.side_effect = RuntimeError("connection refused")
        config = ScraperConfig(niche="salons", location="London")

        lead = scrape_business_site("https://salon.example/", config)

        self.assertEqual(lead["ai_extraction"], "skipped")
        self.assertIn("connection refused", lead["ai_skipped_reason"])

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_slow_model_is_abandoned_after_the_timeout(self, graph_class, fetcher_class, _enrich):
        import threading

        self._fetcher(fetcher_class, "https://salon.example/")
        release = threading.Event()
        graph_class.return_value.run.side_effect = lambda: release.wait(5)
        config = ScraperConfig(niche="salons", location="London")
        from app import scraper

        original = scraper._run_with_timeout
        with patch("app.scraper._run_with_timeout", lambda work, _t, cancel=None: original(work, 0.2, cancel)):
            lead = scrape_business_site("https://salon.example/", config)
        release.set()

        self.assertIn("took longer", lead["ai_skipped_reason"])

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    def test_ai_off_still_rejects_an_unrelated_redirect(self, fetcher_class, _enrich):
        self._fetcher(fetcher_class, "https://platform.example/")
        config = ScraperConfig(niche="salons", location="London", ai_extraction="off")

        with self.assertRaisesRegex(ValueError, "unrelated domain"):
            scrape_business_site("https://salon.example/", config)

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_scraper_passes_json_schema_and_normalizes_result(self, graph_class, fetcher_class, _enrich):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        fetcher_class.return_value.fetch.return_value.url = "https://schema.example/"
        graph_class.return_value.run.return_value = {
            "content": {
                "is_valid_lead": True,
                "business_name": "Schema Salon",
                "website": "https://schema.example/",
                "services": ["Hair"],
            }
        }
        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        lead = scrape_business_site("https://schema.example/", config)

        graph_config = graph_class.call_args.kwargs["config"]
        self.assertEqual(graph_config["llm"]["format"]["type"], "object")
        self.assertEqual(lead["business_name"], "Schema Salon")
        self.assertGreater(lead["lead_score"], 0)

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_ollama_is_given_a_context_window_as_large_as_each_page_chunk(self, graph_class, fetcher_class, _enrich):
        # Ollama keeps only its default window (4096 tokens in 0.24) unless told
        # otherwise, and drops the start of a longer chunk: the part of a page that
        # usually holds the business name and contact links.
        self._fetcher(fetcher_class, "https://salon.example/")
        graph_class.return_value.run.return_value = {"content": {"business_name": "Salon"}}
        config = ScraperConfig(niche="salons", location="London")

        scrape_business_site("https://salon.example/", config)

        llm = graph_class.call_args.kwargs["config"]["llm"]
        self.assertEqual(llm["num_ctx"], 8192)
        self.assertEqual(llm["num_ctx"], llm["model_tokens"])

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_scraper_configures_openai_compatible_model_without_ollama_format(
        self, graph_class, fetcher_class, _enrich
    ):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        fetcher_class.return_value.fetch.return_value.url = "https://api.example/"
        graph_class.return_value.run.return_value = {
            "content": {"business_name": "API Salon", "website": "https://api.example/"}
        }
        config = ScraperConfig(
            niche="salons",
            location="London",
            model="oneapi/paid-model",
            ollama_base_url="https://models.example/v1",
            llm_api_key="secret-key",
        )

        scrape_business_site("https://api.example/", config)

        llm = graph_class.call_args.kwargs["config"]["llm"]
        self.assertEqual(llm["model"], "oneapi/paid-model")
        self.assertEqual(llm["base_url"], "https://models.example/v1")
        self.assertEqual(llm["api_key"], "secret-key")
        self.assertNotIn("format", llm)

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_scraper_preserves_schema_validation_errors(self, graph_class, fetcher_class, _enrich):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        fetcher_class.return_value.fetch.return_value.url = "https://broken.example/"
        graph_class.return_value.run.return_value = {
            "content": {
                "is_valid_lead": True,
                "business_name": "Broken Shape",
                "services": "not-a-list",
            }
        }
        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        lead = scrape_business_site("https://broken.example/", config)

        self.assertFalse(lead["is_valid_lead"])
        self.assertTrue(lead["validation_errors"])
        self.assertIn("not-a-list", lead["raw_output"])

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    def test_scraper_propagates_adaptive_setting_to_llm_source_fetch(self, fetcher_class, _enrich):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        fetcher_class.return_value.fetch.return_value.url = "https://example.com/"
        config = ScraperConfig(
            niche="salons",
            location="London",
            advanced_fetching=False,
        )

        with patch("app.scraper.SmartScraperGraph") as graph:
            graph.return_value.run.return_value = {}
            scrape_business_site("https://example.com/", config)

        self.assertFalse(fetcher_class.call_args.kwargs["advanced_fetching"])

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    def test_scraper_rejects_an_unrelated_redirect_before_llm(self, fetcher_class, _enrich):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        fetcher_class.return_value.fetch.return_value.url = "https://platform.example/"
        config = ScraperConfig(niche="salons", location="London")

        with self.assertRaisesRegex(ValueError, "unrelated domain"):
            scrape_business_site("https://salon.example/", config)

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_emits_typed_summary_and_quality_metrics(self, scrape, search):
        search.return_value = [
            {
                "title": "Example Salon",
                "url": "https://example.com/contact",
                "homepage": "https://example.com/",
                "snippet": "London salon",
                "domain": "example.com",
            }
        ]
        scrape.return_value = {
            "is_valid_lead": True,
            "business_name": "Example Salon",
            "website": "https://example.com/",
            "city_or_area": "London",
            "business_type": "Salon",
            "services": ["Hair"],
            "generic_email": "info@example.com",
            "phone": "123",
            "contact_page": "https://example.com/contact",
            "booking_page": "",
            "instagram_or_social": "",
            "has_online_booking": False,
            "website_quality_note": "",
            "lead_score": 0,
            "lead_reason": "",
            "source_url": "",
            "search_title": "",
            "search_snippet": "",
            "domain": "example.com",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=Path(temp_dir) / "test.db",
                delay_seconds=0,
            )
            output = run_pipeline(config)

        self.assertEqual(output["summary"]["clean_lead_count"], 1)
        self.assertEqual(output["summary"]["clean_yield"], 1.0)
        self.assertEqual(output["summary"]["generic_email_coverage"], 1.0)
        self.assertEqual(output["failed_urls"], [])

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_can_cancel_before_scraping_next_domain(self, scrape, search):
        search.return_value = [
            {
                "title": "One",
                "url": "https://one.example/",
                "homepage": "https://one.example/",
                "snippet": "",
                "domain": "one.example",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = run_pipeline(
                ScraperConfig(
                    niche="salons",
                    location="London",
                    output_dir=Path(temp_dir),
                    database_path=Path(temp_dir) / "test.db",
                    delay_seconds=0,
                ),
                cancel_check=lambda: True,
            )
        scrape.assert_not_called()
        self.assertTrue(output["summary"]["cancelled"])

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_does_not_persist_a_result_without_public_contacts(self, scrape, search):
        search.return_value = [
            {
                "title": "No Contact Studio",
                "url": "https://nocontact.example/",
                "homepage": "https://nocontact.example/",
                "snippet": "London studio",
                "domain": "nocontact.example",
            }
        ]
        scrape.return_value = {
            **self._lead(
            "No Contact Studio",
            "https://nocontact.example/",
            "nocontact.example",
            ),
            "generic_email": "",
            "emails": [],
            "phone": "",
            "phones": [],
            "lead_score": 0,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="studios",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
            )
            run_pipeline(config)
            repository = RunRepository(database_path)
            run_id = repository.list_runs()[0]["id"]
            candidates = repository.list_candidates(run_id)
            leads = repository.load_leads(run_id)
            repository.engine.dispose()

        self.assertEqual(candidates[0]["status"], "no_contact")
        self.assertEqual(leads, [])

    @patch("app.pipeline.save_run", side_effect=OSError("disk full"))
    @patch("app.pipeline.search_business_sites", return_value=[])
    def test_export_disk_error_marks_run_failed(self, _search, _save):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
            )
            with self.assertRaisesRegex(OSError, "disk full"):
                run_pipeline(config)
            repository = RunRepository(database_path)
            try:
                self.assertEqual(repository.list_runs()[0]["status"], "failed")
            finally:
                repository.engine.dispose()

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_resume_keeps_completed_leads_and_processes_pending(self, scrape, search):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
                reuse_existing_leads=False,
            )
            repository = RunRepository(database_path)
            run_id = repository.create_run(config)
            sites = [
                {
                    "title": "One",
                    "url": "https://one-example.com/",
                    "homepage": "https://one-example.com/",
                    "snippet": "",
                    "domain": "one-example.com",
                },
                {
                    "title": "Two",
                    "url": "https://two-example.com/",
                    "homepage": "https://two-example.com/",
                    "snippet": "",
                    "domain": "two-example.com",
                },
            ]
            repository.add_candidates(run_id, sites)
            first_id = repository.claim(run_id, "one-example.com")
            first_lead = self._lead("One", "https://one-example.com/", "one-example.com")
            repository.complete(first_id, first_lead)
            repository.engine.dispose()
            scrape.return_value = self._lead("Two", "https://two-example.com/", "two-example.com")

            output = run_pipeline(config, resume_run_id=run_id)

        search.assert_not_called()
        scrape.assert_called_once()
        self.assertEqual(output["summary"]["clean_lead_count"], 2)

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_reuse_mode_uses_cached_lead_without_scraping(self, scrape, search):
        search.return_value = [
            {
                "title": "Existing",
                "url": "https://existing.co.uk/",
                "homepage": "https://existing.co.uk/",
                "snippet": "London salon",
                "domain": "existing.co.uk",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
                discovery_mode="reuse",
            )
            repository = RunRepository(database_path)
            old_run = repository.create_run(config)
            repository.add_candidates(old_run, search.return_value)
            candidate_id = repository.claim(old_run, "existing.co.uk")
            repository.complete(
                candidate_id,
                self._lead("Cached", "https://existing.co.uk/", "existing.co.uk"),
            )
            repository.engine.dispose()

            output = run_pipeline(config)

        scrape.assert_not_called()
        self.assertEqual(output["clean_leads"][0]["business_name"], "Cached")

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_refresh_mode_scrapes_previously_completed_domain(self, scrape, search):
        site = {
            "title": "Existing",
            "url": "https://existing.co.uk/",
            "homepage": "https://existing.co.uk/",
            "snippet": "London salon",
            "domain": "existing.co.uk",
        }
        search.return_value = [site]
        scrape.return_value = self._lead("Refreshed", site["homepage"], site["domain"])
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            cached_config = ScraperConfig(
                niche="salons",
                location="London",
                database_path=database_path,
            )
            repository = RunRepository(database_path)
            old_run = repository.create_run(cached_config)
            repository.add_candidates(old_run, [site])
            candidate_id = repository.claim(old_run, site["domain"])
            repository.complete(
                candidate_id,
                self._lead("Cached", site["homepage"], site["domain"]),
            )
            repository.engine.dispose()
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
                discovery_mode="refresh",
            )

            output = run_pipeline(config)

        scrape.assert_called_once()
        self.assertEqual(output["clean_leads"][0]["business_name"], "Refreshed")

    @patch("app.pipeline.scrape_business_site")
    def test_superseded_worker_does_not_write_lead_export_or_terminal_status(self, scrape):
        site = {
            "title": "Existing",
            "url": "https://existing.co.uk/",
            "homepage": "https://existing.co.uk/",
            "snippet": "London salon",
            "domain": "existing.co.uk",
        }
        scrape.return_value = self._lead("Stale result", site["homepage"], site["domain"])
        checks = iter([False, True])
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=root / "exports",
                database_path=database_path,
                delay_seconds=0,
            )
            repository = RunRepository(database_path)
            run_id = repository.create_run(config)
            repository.add_candidates(run_id, [site])
            repository.begin_run(run_id)
            repository.engine.dispose()

            run_pipeline(
                config,
                resume_run_id=run_id,
                cancel_check=lambda: next(checks),
                active_check=lambda: False,
            )

            repository = RunRepository(database_path)
            status = repository.run_status(run_id)
            candidates = repository.list_candidates(run_id)
            leads = repository.load_leads(run_id)
            repository.engine.dispose()
            exports_created = (root / "exports").exists()

        self.assertEqual(status["status"], "running")
        self.assertEqual(candidates[0]["status"], "processing")
        self.assertEqual(leads, [])
        self.assertFalse(exports_created)

    @staticmethod
    def _lead(name: str, website: str, domain: str) -> dict:
        return {
            "is_valid_lead": True,
            "business_name": name,
            "website": website,
            "city_or_area": "London",
            "business_type": "Salon",
            "services": ["Hair"],
            "generic_email": f"info@{domain}",
            "phone": "123",
            "contact_page": f"{website}contact",
            "booking_page": "",
            "instagram_or_social": "",
            "has_online_booking": False,
            "website_quality_note": "",
            "lead_score": 8,
            "lead_reason": "Verified",
            "source_url": website,
            "search_title": name,
            "search_snippet": "",
            "domain": domain,
            "field_evidence": {},
            "enrichment_errors": [],
        }


if __name__ == "__main__":
    unittest.main()


def test_scrapegraphai_telemetry_is_disabled() -> None:
    """Page content and URLs must never be sent to ScrapeGraphAI's telemetry service."""
    from scrapegraphai.telemetry import telemetry

    import app.scraper  # noqa: F401

    assert telemetry.is_telemetry_enabled() is False


def test_site_name_reads_the_home_page_name_without_the_model():
    from bs4 import BeautifulSoup

    from app.enrichment import site_name

    cases = {
        '<meta property="og:site_name" content="Fortnum &amp; Mason"><title>Shop</title>': "Fortnum & Mason",
        "<title>Bettys | Café Tea Rooms</title>": "Bettys",
        "<title>Home - Joe's Barbers</title>": "Joe's Barbers",
        "<title>Welcome to Smith Dental</title>": "Smith Dental",
        "<title>Home</title>": "",
    }
    for html, expected in cases.items():
        assert site_name(BeautifulSoup(html, "lxml")) == expected


def test_scrapegraphai_passes_the_context_window_on_to_ollama():
    """No mocks: the real ScrapeGraphAI graph must hand num_ctx to its ChatOllama."""
    from scrapegraphai.graphs import SmartScraperGraph

    from app.config import MODEL_CONTEXT_TOKENS

    graph = SmartScraperGraph(
        prompt="Find the business name.",
        source="<html><body><h1>Salon</h1></body></html>",
        config={
            "llm": {
                "model": "ollama/llama3.2:3b",
                "temperature": 0,
                "model_tokens": MODEL_CONTEXT_TOKENS,
                "num_ctx": MODEL_CONTEXT_TOKENS,
                "base_url": "http://127.0.0.1:11434",
            },
            "verbose": False,
            "headless": True,
        },
    )

    assert graph.llm_model.num_ctx == MODEL_CONTEXT_TOKENS
    assert graph.model_token == MODEL_CONTEXT_TOKENS
