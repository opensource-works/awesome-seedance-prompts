from __future__ import annotations

import copy
import os
import sys
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import catalog  # noqa: E402
import discover  # noqa: E402


class DiscoveryWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = catalog.read_json(ROOT / "config" / "query-matrix.json")
        cls.config = catalog.read_json(ROOT / "config" / "collection.json")

    def empty_catalog(self):
        return {"actors": {}, "sources": {}, "candidates": {}}

    def test_historical_cutoff_is_fixed_and_exclusive(self):
        window = discover.discovery_window(
            self.matrix, "historical", "2026-08-20T00:00:00Z",
        )
        self.assertEqual("2026-02-07T00:00:00Z", window["from"])
        self.assertEqual("2026-08-11T12:30:00Z", window["through_exclusive"])
        self.assertTrue(discover.in_discovery_window("2026-08-11T12:29:59Z", window))
        self.assertFalse(discover.in_discovery_window("2026-08-11T12:30:00Z", window))

    def test_ongoing_window_is_separate_and_never_crosses_cutoff(self):
        window = discover.discovery_window(
            self.matrix, "ongoing", "2026-08-18T12:30:00Z",
        )
        self.assertEqual("ongoing", window["kind"])
        self.assertEqual("2026-08-11T12:30:00Z", window["from"])
        self.assertEqual("2026-08-18T12:29:45Z", window["through_exclusive"])
        self.assertEqual("2026-08-11T12:30:00Z", window["requested_from"])
        self.assertTrue(discover.in_discovery_window("2026-08-11T12:30:00Z", window))
        self.assertTrue(discover.in_discovery_window("2026-08-18T12:29:44Z", window))
        self.assertFalse(discover.in_discovery_window("2026-08-18T12:29:45Z", window))

    def test_x_request_and_retention_use_same_historical_bounds(self):
        value = self.empty_catalog()
        window = discover.discovery_window(self.matrix, "historical", "2026-08-20T00:00:00Z")
        payload = {
            "data": [
                {"id": "1001", "text": "Seedance", "created_at": "2026-08-11T12:29:59Z",
                 "author_id": "u1"},
                {"id": "1002", "text": "Seedance", "created_at": "2026-08-11T12:30:00Z",
                 "author_id": "u1"},
            ],
            "includes": {"users": [{"id": "u1", "username": "tester"}]},
            "meta": {},
        }
        seen = []

        def fake_request(url, **_kwargs):
            seen.append(url)
            return payload, 200

        with mock.patch.dict(os.environ, {"X_BEARER_TOKEN": "test"}), mock.patch.object(
            discover, "request_json", side_effect=fake_request
        ):
            count, errors, stats = discover.discover_x(
                value, [{"id": "q", "query": "Seedance"}], self.matrix, self.config,
                window=window, max_pages=1, run_id="run", observed_at="2026-08-20T00:00:00Z",
            )
        params = urllib.parse.parse_qs(urllib.parse.urlparse(seen[0]).query)
        self.assertEqual([window["from"]], params["start_time"])
        self.assertEqual([window["through_exclusive"]], params["end_time"])
        self.assertEqual(1, count)
        self.assertEqual([], errors)
        self.assertEqual(1, stats["filtered_outside_window"])

    def test_reddit_results_are_filtered_client_side(self):
        value = self.empty_catalog()
        window = discover.discovery_window(self.matrix, "ongoing", "2026-08-12T12:30:00Z")

        def epoch(value):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

        payload = {"data": {"children": [
            {"data": {"id": "old", "name": "t3_old", "permalink": "/comments/old",
                      "author": "tester", "created_utc": epoch("2026-08-11T12:29:59Z"),
                      "title": "Seedance", "is_video": True}},
            {"data": {"id": "new", "name": "t3_new", "permalink": "/comments/new",
                      "author": "tester", "created_utc": epoch("2026-08-11T12:30:00Z"),
                      "title": "Seedance", "is_video": True}},
        ], "after": None}}
        with mock.patch.object(discover, "reddit_token", return_value="token"), mock.patch.object(
            discover, "request_json", return_value=(payload, 200)
        ):
            count, errors, stats = discover.discover_reddit(
                value, [{"id": "q", "query": "Seedance"}], self.matrix, self.config,
                window=window, max_pages=1, run_id="run", observed_at="2026-08-12T12:30:00Z",
            )
        self.assertEqual(1, count)
        self.assertEqual([], errors)
        self.assertEqual(1, stats["filtered_outside_window"])
        self.assertIn("reddit:t3_new", value["candidates"])
        self.assertNotIn("reddit:t3_old", value["candidates"])


if __name__ == "__main__":
    unittest.main()
