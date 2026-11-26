from __future__ import annotations

import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from unittest import TestCase, mock

from app.local_data import (
    LocalDataService,
    LocalDataSync,
    _data_timestamp,
    _expand_niche,
    _run_hidden,
    _sql_literal,
)
from app.pipeline import _has_local_seed, _lead_from_osm

OSM_ROW = {
    "osm_type": "N",
    "osm_id": 42,
    "name": "Elm Beauty Rooms",
    "category": "shop",
    "category_value": "beauty",
    "website": "",
    "phone": "020 7946 0102",
    "email": "hello@elm.test",
    "address": "14 Sample Street",
    "city": "London",
    "postcode": "W1F 8AA",
    "latitude": 51.51,
    "longitude": -0.14,
}


class LocalDataTests(TestCase):
    def test_osm_row_becomes_structured_candidate(self):
        candidate = LocalDataService._candidate(OSM_ROW)

        self.assertEqual(candidate["source"], "osm_local")
        self.assertEqual(candidate["domain"], "osm-N-42")
        self.assertEqual(candidate["osm_url"], "https://www.openstreetmap.org/node/42")
        self.assertEqual(candidate["phone"], "020 7946 0102")

    def test_phone_only_candidate_becomes_valid_lead_without_scraping(self):
        candidate = LocalDataService._candidate({**OSM_ROW, "email": ""})
        lead = _lead_from_osm(candidate)

        self.assertTrue(lead["is_valid_lead"])
        self.assertEqual(lead["business_name"], "Elm Beauty Rooms")
        self.assertEqual(lead["phones"], ["020 7946 0102"])
        self.assertGreaterEqual(lead["lead_score"], 4)

    def test_local_contacts_are_normalized_and_unrelated_email_is_rejected(self):
        candidate = LocalDataService._candidate(
            {
                **OSM_ROW,
                "website": "https://elmbeauty.co.uk/",
                "email": "sales@unrelated.co.uk",
                "phone": "tel:+44%2020%207946%200102",
            }
        )

        lead = _lead_from_osm(candidate)

        self.assertEqual(lead["generic_email"], "")
        self.assertNotIn("generic_email", lead["field_evidence"])
        self.assertEqual(lead["phones"], ["+44 20 7946 0102"])

    def test_local_coordinates_survive_into_the_run_and_its_exports(self):
        # The run's map plots leads by these; clean_leads used to drop them.
        from app.normalizer import clean_leads
        from app.pipeline import _merge_osm_seed

        local = clean_leads([_lead_from_osm(LocalDataService._candidate(OSM_ROW))])[0]
        self.assertEqual((local["latitude"], local["longitude"]), ("51.51", "-0.14"))

        web_lead = {"business_name": "Elm Beauty Rooms", "website": "https://elmbeauty.co.uk/", "emails": [], "phones": []}
        _merge_osm_seed(web_lead, {**LocalDataService._candidate(OSM_ROW), "homepage": "https://elmbeauty.co.uk/"})
        self.assertEqual((web_lead["latitude"], web_lead["longitude"]), ("51.51", "-0.14"))

    def test_hybrid_candidate_keeps_its_local_seed_for_enrichment(self):
        self.assertTrue(_has_local_seed({"source": "hybrid", "sources": ["web", "local"]}))

    def test_sql_literal_escapes_user_input(self):
        self.assertEqual(_sql_literal("King's Cross"), "'King''s Cross'")

    def test_common_market_language_expands_to_osm_categories(self):
        terms = _expand_niche("HVAC contractors")

        self.assertIn("air conditioning", terms)
        self.assertIn("heating", terms)

    def test_market_qualifiers_do_not_drive_fuzzy_matches(self):
        terms = _expand_niche("independent cafes")

        self.assertIn("cafe", terms)
        self.assertNotIn("independent cafes", terms)

    @mock.patch("app.local_data.subprocess.run")
    def test_windows_child_processes_never_open_a_console(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "{}", "")

        _run_hidden(["wsl", "--", "true"], timeout=2)

        options = run.call_args.kwargs
        self.assertTrue(options["capture_output"])
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["errors"], "replace")
        if sys.platform == "win32":
            self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
            self.assertTrue(options["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)

    @mock.patch("app.local_data._run_hidden")
    def test_manual_update_returns_at_once_but_waits_for_the_service_in_the_background(self, run):
        released = threading.Event()
        started = threading.Event()

        def slow_update(command, timeout):
            started.set()
            released.wait(5)
            return subprocess.CompletedProcess(command, 0, "", "")

        run.side_effect = slow_update
        sync = LocalDataSync()
        with mock.patch("app.local_data.LOCAL_DATA_SYNC", sync), \
                mock.patch.object(LocalDataService, "_use_wsl_bridge", True):
            result = LocalDataService().request_update()
            self.assertTrue(started.wait(5))
            self.assertEqual(result["status"], "started")
            self.assertTrue(sync.running)
            # A second request while the first runs does not start another update.
            self.assertEqual(LocalDataService().request_update()["status"], "running")
            released.set()
            sync._worker.join(5)

        command = run.call_args.args[0]
        # Waiting on systemctl is what keeps WSL running until the update is complete;
        # --no-block let WSL shut down and cut the update off part-way.
        self.assertEqual(command[-3:], ["systemctl", "start", "leadroom-osm-update.service"])
        self.assertNotIn("--no-block", command)
        self.assertFalse(sync.running)
        self.assertEqual(sync.last_error, "")

    @mock.patch("app.local_data._run_hidden")
    def test_failed_update_is_reported(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "failed")
        sync = LocalDataSync()
        sync.start()
        sync._worker.join(5)

        self.assertIn("journalctl", sync.last_error)

    def test_automatic_update_runs_only_when_the_data_is_stale(self):
        now = datetime(2026, 11, 24, 12, tzinfo=UTC)
        sync = LocalDataSync()
        status = {"ready": True, "update_status": "idle"}

        fresh = {**status, "data_timestamp": "2026-11-23T21:21:17Z"}
        stale = {**status, "data_timestamp": "2026-07-29T20:20:57Z"}
        self.assertFalse(sync.due(fresh, now))
        self.assertTrue(sync.due(stale, now))
        self.assertTrue(sync.due({**status, "data_timestamp": None}, now))
        self.assertFalse(sync.due({**stale, "ready": False}, now))
        self.assertFalse(sync.due({**stale, "update_status": "running"}, now))
        self.assertFalse(sync.due({**stale, "update_status": "not_configured"}, now))

        sync.last_attempt = now - timedelta(minutes=10)
        self.assertFalse(sync.due(stale, now))
        sync.last_attempt = now - timedelta(hours=2)
        self.assertTrue(sync.due(stale, now))
        sync.last_error = "failed"
        self.assertFalse(sync.due(stale, now))

    def test_data_date_comes_from_the_replication_state(self):
        self.assertEqual(
            _data_timestamp({"import_timestamp": "2026-07-29T20:20:39Z", "replication_timestamp": "2026-11-23T21:21:17Z"}),
            "2026-11-23T21:21:17Z",
        )
        self.assertEqual(_data_timestamp({"import_timestamp": "2026-07-29T20:20:39Z"}), "2026-07-29T20:20:39Z")
        self.assertIsNone(_data_timestamp({}))

    def test_a_running_status_left_by_an_interrupted_update_is_not_trusted(self):
        recorded = {"ready": True, "update_status": "running", "update_message": "Downloading"}
        with mock.patch.object(LocalDataService, "_status", return_value=dict(recorded)), \
                mock.patch.object(LocalDataService, "_use_wsl_bridge", True), \
                mock.patch.object(LocalDataService, "update_service_active", return_value=False), \
                mock.patch("app.local_data.LOCAL_DATA_SYNC", LocalDataSync()):
            status = LocalDataService().status()

        self.assertEqual(status["update_status"], "idle")
