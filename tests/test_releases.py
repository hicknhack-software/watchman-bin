import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("releases", "scripts/releases.py")
releases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(releases)


def release(day, *, mirrored=False, draft=False, prerelease=False, assets=True):
    tag = f"v2026.10.{day:02}.00"
    date = f"2026-10-{day:02}T15:00:00Z"
    archive = releases.asset_name(tag)
    return {
        "id": day, "tag_name": tag, "published_at": date, "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": archive}, {"name": archive + ".sha256"}] if assets else [],
        "body": f"<!-- watchman-bin upstream-published-at: {date} -->" if mirrored else "",
    }


class DiscoveryTest(unittest.TestCase):
    def test_first_run_only_builds_latest_stable(self):
        upstream = [release(20, prerelease=True), release(19), release(12)]
        self.assertEqual(releases.pending(upstream, []), [upstream[1]])

    def test_catches_up_in_order_and_ignores_older_history(self):
        upstream = [release(21), release(19), release(12), release(5)]
        local = [release(12, mirrored=True)]
        self.assertEqual(releases.pending(upstream, local), [upstream[1], upstream[0]])

    def test_no_rebuild_for_complete_releases(self):
        self.assertEqual(releases.pending([release(19)], [release(19, mirrored=True)]), [])

    def test_failed_older_release_is_not_lost_when_newer_one_succeeds(self):
        upstream = [release(21), release(19), release(12)]
        local = [release(12, mirrored=True), release(21, mirrored=True)]
        self.assertEqual(releases.pending(upstream, local), [upstream[1]])

    def test_drafts_and_incomplete_uploads_are_retried(self):
        upstream = [release(21), release(19), release(12)]
        local = [release(12, mirrored=True), release(19, mirrored=True, draft=True),
                 release(21, mirrored=True, assets=False)]
        self.assertEqual(releases.pending(upstream, local), [upstream[1], upstream[0]])

    def test_upstream_drafts_and_prereleases_are_skipped(self):
        upstream = [release(21, draft=True), release(20, prerelease=True), release(19)]
        self.assertEqual(releases.pending(upstream, [release(19, mirrored=True)]), [])

    def test_late_published_release_is_found(self):
        upstream = [release(12), release(21), release(19)]
        self.assertEqual(releases.pending(upstream, [release(19, mirrored=True)]), [upstream[1]])

    def test_empty_upstream(self):
        self.assertEqual(releases.pending([], []), [])

    def test_manual_historical_build_does_not_trigger_a_historical_backlog(self):
        backfill = release(5, mirrored=True)
        backfill["id"] = 99
        local = [release(19, mirrored=True), backfill]
        upstream = [release(21), release(19), release(12), release(5)]
        self.assertEqual(releases.pending(upstream, local), [upstream[0]])


class PublishingTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        original = os.getcwd()
        os.chdir(directory.name)
        self.addCleanup(os.chdir, original)
        pathlib.Path("dist").mkdir()
        self.upstream = release(19)
        self.upstream.update(name="Watchman October Release", html_url="https://example.test/release")
        self.tag = self.upstream["tag_name"]
        archive = pathlib.Path("dist") / releases.asset_name(self.tag)
        archive.touch()
        archive.with_name(archive.name + ".sha256").touch()
        self.missing = releases.urllib.error.HTTPError("url", 404, "Not found", {}, None)
        self.addCleanup(self.missing.close)
        environment = mock.patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "example/watchman-bin", "GITHUB_SHA": "123abc",
        })
        environment.start()
        self.addCleanup(environment.stop)

    @mock.patch.object(releases.subprocess, "run")
    @mock.patch.object(releases, "api")
    def test_create_draft_upload_then_publish_with_upstream_name(self, api, run):
        api.side_effect = [self.upstream, self.missing]
        releases.publish(self.tag)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([command[2] for command in commands], ["create", "upload", "edit"])
        self.assertIn("--draft", commands[0])
        self.assertIn("Watchman October Release", commands[0])
        self.assertIn("--draft=false", commands[2])

    @mock.patch.object(releases.subprocess, "run")
    @mock.patch.object(releases, "api")
    def test_existing_release_is_repaired(self, api, run):
        api.side_effect = [self.upstream, release(19, draft=True)]
        releases.publish(self.tag)
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ["upload", "edit"])

    @mock.patch.object(releases.subprocess, "run")
    @mock.patch.object(releases, "api")
    def test_failed_upload_does_not_publish_draft(self, api, run):
        api.side_effect = [self.upstream, self.missing]
        run.side_effect = [None, RuntimeError("Upload failed")]
        with self.assertRaises(RuntimeError):
            releases.publish(self.tag)
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ["create", "upload"])

    @mock.patch.object(releases.subprocess, "run")
    @mock.patch.object(releases, "api")
    def test_missing_checksum_prevents_release_creation(self, api, run):
        api.return_value = self.upstream
        next(pathlib.Path("dist").glob("*.sha256")).unlink()
        with self.assertRaises(FileNotFoundError):
            releases.publish(self.tag)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
