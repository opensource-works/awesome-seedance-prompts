from __future__ import annotations

import copy
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import catalog  # noqa: E402
import hydrate  # noqa: E402
import prepare_uploads  # noqa: E402
import review  # noqa: E402


class HydrationPrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = catalog.read_json(ROOT / "data" / "catalog.json")
        cls.at = "2026-08-11T12:00:00Z"
        cls.reviewer = "act_repository_opensource-works"
        cls.review_evidence = ["ev_editorial_legacy_migration_20260811"]

    def pending(self, value: dict) -> str:
        return next(
            source_id for source_id, candidate in value["candidates"].items()
            if candidate["review"]["state"] == "pending"
        )

    def test_prompt_proposal_is_metadata_only_and_human_acceptance_is_explicit(self):
        value = copy.deepcopy(self.base)
        hydrate.ensure_automation(value, self.at)
        source_id = self.pending(value)
        sentinel = "PRIVATE-PROMPT-SENTINEL-90817"
        raw = "Prompt: " + " ".join([sentinel] * 8)
        source = value["sources"][source_id]
        source["text"] = {"status": "available", "value": raw, "language": "en"}
        source["media_observations"] = [{
            "source_media_id": "x-media:privacy-test", "kind": "video", "position": 0,
            "direct_url": "https://video.twimg.com/ext_tw_video/privacy.mp4",
            "thumbnail_url": "https://pbs.twimg.com/ext_tw_video_thumb/privacy.jpg",
            "variants": [{
                "url": "https://video.twimg.com/ext_tw_video/privacy.mp4",
                "container": "mp4", "width": 640, "height": 360,
            }],
            "observed_at": self.at,
        }]
        cache = hydrate.initialize_volatile_cache(value, self.at)

        hydrate.scrub_volatile_catalog(value, cache, self.at)
        hydrate.maybe_capture_root_prompt(
            value, source_id, self.at, text=raw, volatile_cache=cache,
        )

        observation = value["candidates"][source_id]["prompt_observation"]
        self.assertNotIn("text", observation)
        self.assertIsNone(value["sources"][source_id]["text"]["value"])
        self.assertIsNone(value["sources"][source_id]["media_observations"][0]["direct_url"])
        self.assertNotIn(sentinel, json.dumps(value, ensure_ascii=False))
        self.assertIn(sentinel, cache["prompts"][observation["cache_key"]]["text"])
        self.assertFalse(any(
            item.get("canonical_source_id") == source_id
            for item in value["items"].values()
        ))

        with self.assertRaises(review.ReviewError):
            review.include_candidate(
                value, source_id, reasons=["meets_scope"],
                evidence_ids=self.review_evidence, actor=self.reviewer, at=self.at,
                note="must decide prompt", requested_item_id=None,
                title="Reviewed privacy test",
            )

        payload = cache["prompts"][observation["cache_key"]]
        item_id = review.include_candidate(
            value, source_id, reasons=["meets_scope"],
            evidence_ids=self.review_evidence, actor=self.reviewer, at=self.at,
            note="accepted after reading", requested_item_id=None,
            prompt_decision="accept", prompt_payload=payload,
            title="Reviewed privacy test",
        )
        item = value["items"][item_id]
        self.assertIn(sentinel, item["prompt"]["text"])
        self.assertNotIn("prompt_observation", value["candidates"][source_id])
        self.assertEqual("unknown", item["attribution"]["original_video_creators"][0]["status"])
        self.assertEqual("unknown", item["attribution"]["prompt_authors"][0]["status"])
        self.assertEqual("unknown", item["rights"]["video_republication"]["status"])
        self.assertEqual("unknown", item["rights"]["prompt_republication"]["status"])

    def test_same_poster_comment_text_is_private_and_only_proposes_prompt(self):
        value = copy.deepcopy(self.base)
        hydrate.ensure_automation(value, self.at)
        root_id = self.pending(value)
        root = value["sources"][root_id]
        actor = copy.deepcopy(value["actors"][root["posted_by_actor_id"]])
        sentinel = "COMMENT-PROMPT-PRIVATE-441"
        text = "Prompt: " + " ".join([sentinel] * 10)
        cache = hydrate.initialize_volatile_cache(value, self.at)
        comment_id = hydrate.store_comment(
            value, platform=root["platform"], native_id="privacy-comment-441",
            url=(
                "https://x.com/example/status/privacy-comment-441"
                if root["platform"] == "x"
                else "https://www.reddit.com/comments/example/_/privacy-comment-441/"
            ),
            parent_source_id=root_id, text=text, actor=actor, at=self.at,
            posted_at=self.at, volatile_cache=cache,
        )
        hydrate.maybe_capture_comment_prompt(
            value, root_id, comment_id, text=text, at=self.at,
            volatile_cache=cache,
        )
        self.assertIsNone(value["sources"][comment_id]["text"]["value"])
        observation = value["candidates"][root_id]["prompt_observation"]
        self.assertEqual(comment_id, observation["source_id"])
        self.assertNotIn("text", observation)
        self.assertNotIn(sentinel, json.dumps(value, ensure_ascii=False))
        self.assertIn(sentinel, cache["prompts"][observation["cache_key"]]["text"])

    def test_scrub_fails_closed_without_cache_or_explicit_discard(self):
        value = copy.deepcopy(self.base)
        source = value["sources"][self.pending(value)]
        source["text"] = {"status": "available", "value": "private raw text", "language": None}
        with self.assertRaises(ValueError):
            hydrate.scrub_volatile_catalog(value, None, self.at)
        hydrate.scrub_volatile_catalog(value, None, self.at, discard=True)
        self.assertIsNone(source["text"]["value"])

    def test_cache_file_is_0600_without_chmod_on_existing_external_parent(self):
        value = copy.deepcopy(self.base)
        cache = hydrate.initialize_volatile_cache(value, self.at)
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "shared"
            parent.mkdir()
            parent.chmod(0o755)
            path = parent / "cache.json"
            hydrate.write_volatile_cache(path, cache)
            self.assertEqual(0o755, stat.S_IMODE(parent.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_decided_prompt_payload_is_atomically_removed(self):
        value = copy.deepcopy(self.base)
        source_id = self.pending(value)
        cache = hydrate.initialize_volatile_cache(value, self.at)
        cache["prompts"]["decision-key"] = {"text": "private"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cache.json"
            hydrate.write_volatile_cache(path, cache)
            review.consume_prompt_payload(value, path, "decision-key")
            rewritten = catalog.read_json(path)
            self.assertNotIn("decision-key", rewritten["prompts"])
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_reject_remains_possible_without_ephemeral_cache(self):
        value = copy.deepcopy(self.base)
        hydrate.ensure_automation(value, self.at)
        source_id = self.pending(value)
        raw = "Prompt: " + "reject-me " * 15
        cache = hydrate.initialize_volatile_cache(value, self.at)
        hydrate.maybe_capture_root_prompt(
            value, source_id, self.at, text=raw, volatile_cache=cache,
        )
        review.include_candidate(
            value, source_id, reasons=["meets_scope"],
            evidence_ids=self.review_evidence, actor=self.reviewer, at=self.at,
            note="reject proposal", requested_item_id=None,
            prompt_decision="reject", prompt_payload=None, title="Reviewed title",
        )
        self.assertNotIn("prompt_observation", value["candidates"][source_id])
        item_id = value["candidates"][source_id]["review"]["item_id"]
        self.assertEqual("unavailable", value["items"][item_id]["prompt"]["status"])

    def test_weekly_workflow_uses_one_private_cache_and_captures_comments(self):
        workflow = (ROOT / ".github" / "workflows" / "refresh.yml").read_text()
        self.assertGreaterEqual(workflow.count("--volatile-cache .cache/media-locators.json"), 3)
        self.assertGreaterEqual(workflow.count("--with-comments"), 2)
        self.assertIn("--x-comment-mode recent", workflow)

    def test_upload_cache_rejects_non_platform_media_hosts(self):
        source = {"id": "x:1", "platform": "x"}
        observation = {"source_media_id": "x-media:1", "direct_url": None, "variants": []}
        with self.assertRaises(ValueError):
            prepare_uploads.overlay_volatile_observation(source, observation, {
                "x:1/x-media:1": {
                    "source_id": "x:1", "source_media_id": "x-media:1",
                    "direct_url": "https://127.0.0.1/private.mp4", "variants": [],
                }
            })

    def test_pending_only_selection_also_refreshes_rights_cleared_mirror_sources(self):
        value = copy.deepcopy(self.base)
        item = next(iter(value["items"].values()))
        source_id = item["canonical_source_id"]
        item["curation"]["status"] = "approved"
        item["rights"]["video_republication"].update({
            "status": "granted", "granted_scopes": ["download", "mirror_r2"],
        })
        for media in item.get("media") or []:
            media["source_id"] = source_id
            media["delivery"]["mirrors"] = []
        self.assertTrue(hydrate.source_needs_mirror_locator(value, source_id))


if __name__ == "__main__":
    unittest.main()
