from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from gitlab_agent import history_scan
from gitlab_agent.history_scan import HistoryScanError, scan_history_secrets
from gitlab_agent.secret_scan import scan_added_diff_for_secrets, redact_sensitive_text


def dummy_token() -> str:
    # Deliberately fabricated and assembled to keep source/history scanners quiet.
    return "gl" + "pat-" + "notARealCredential0123456789"


def patch_text(line: str) -> str:
    return "diff --git a/a.txt b/a.txt\n--- /dev/null\n+++ b/a.txt\n@@ -0,0 +1 @@\n+" + line + "\n"


class SecretScanRegressionTests(unittest.TestCase):
    def test_placeholder_word_does_not_hide_an_actual_match(self):
        for word in ("EXAMPLE", "YOUR_TOKEN", "YOUR_KEY", "REPLACE_ME", "xxxxxxxx", "<token>"):
            with self.subTest(word=word):
                findings = scan_added_diff_for_secrets(patch_text(f"{word}={dummy_token()}"))
                self.assertTrue(findings)
                self.assertNotIn(dummy_token(), json.dumps(findings))

    def test_placeholder_and_secret_on_same_line(self):
        self.assertTrue(scan_added_diff_for_secrets(
            patch_text('template="<token>"; real="' + dummy_token() + '"'),
        ))

    def test_plain_placeholder_without_credential_shape_is_not_a_finding(self):
        self.assertEqual(scan_added_diff_for_secrets(patch_text('TOKEN="<token>"')), [])

    def test_added_lines_starting_with_pluses_are_not_misread_as_headers(self):
        for prefix in ("++", "+++ ", "++ b/"):
            with self.subTest(prefix=prefix):
                self.assertTrue(scan_added_diff_for_secrets(patch_text(prefix + dummy_token())))

    def test_removed_and_context_lines_are_not_new_findings(self):
        text = patch_text("safe") + "-" + dummy_token() + "\n " + dummy_token() + "\n"
        self.assertEqual(scan_added_diff_for_secrets(text), [])

    def test_unicode_line_separator_does_not_drop_part_of_added_line(self):
        self.assertTrue(scan_added_diff_for_secrets(patch_text("safe\u2028" + dummy_token())))

    def test_findings_omit_source_content_and_record_commit(self):
        commit = "a" * 40
        findings = scan_added_diff_for_secrets("commit " + commit + "\n" + patch_text(dummy_token()))
        self.assertEqual(findings[0]["commit_sha"], commit)
        self.assertEqual(findings[0]["path"], "a.txt")
        self.assertEqual(findings[0]["line"], "[REDACTED:GitLab PAT]")

    def test_quoted_generic_secret_assignments_are_redacted(self):
        for line in ('PASSWORD="opaque value"', "PASSWORD='opaque value'", '"API_KEY": "opaque value"'):
            with self.subTest(line=line):
                text, kinds = redact_sensitive_text(line)
                self.assertNotIn("opaque value", text)
                self.assertTrue(kinds)

    def test_ansi_embedded_in_credential_is_removed_before_detection(self):
        token = dummy_token()
        text = token[:8] + "\x1b[31m" + token[8:] + "\x1b[0m"
        self.assertTrue(scan_added_diff_for_secrets(patch_text(text)))
        self.assertNotIn(token, redact_sensitive_text(text)[0])


class HistoryScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "History Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        (self.repo / "readme.txt").write_text("baseline\n", encoding="utf-8")
        self.base = self.commit("base")

    def git(self, *args, cwd=None):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=env,
                              text=True, capture_output=True, check=True, timeout=20).stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def scan(self, **kwargs):
        return scan_history_secrets(worktree=self.repo, base_sha=self.base,
                                    head_sha=self.git("rev-parse", "HEAD"), **kwargs)

    def add_then_remove(self, content=None, name="secret.txt"):
        (self.repo / name).write_text(content or dummy_token() + "\n", encoding="utf-8")
        introduced = self.commit("introduce")
        (self.repo / name).unlink()
        self.commit("remove")
        return introduced

    def test_add_then_remove_is_detected_when_final_diff_is_empty(self):
        introduced = self.add_then_remove()
        self.assertEqual(self.git("diff", self.base, "HEAD"), "")
        result = self.scan()
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["commit_count"], 2)
        self.assertEqual(result["findings"][0]["commit_sha"], introduced)
        self.assertNotIn(dummy_token(), json.dumps(result))

    def test_initial_and_clean_history_are_valid(self):
        self.assertEqual(self.scan()["commit_count"], 0)
        (self.repo / "safe.txt").write_text("ordinary change\n", encoding="utf-8")
        self.commit("safe")
        self.assertEqual(self.scan()["findings"], [])

    def test_empty_commits_are_counted(self):
        self.commit("empty")
        self.assertEqual(self.scan()["commit_count"], 1)

    def test_merge_resolution_only_secret_is_scanned(self):
        self.git("checkout", "-b", "side")
        (self.repo / "side.txt").write_text("side\n", encoding="utf-8")
        self.commit("side")
        self.git("checkout", "main")
        (self.repo / "main.txt").write_text("main\n", encoding="utf-8")
        self.commit("main")
        self.git("merge", "--no-ff", "--no-commit", "side")
        (self.repo / "secret.txt").write_text(dummy_token(), encoding="utf-8")
        merged = self.commit("merge resolution")
        (self.repo / "secret.txt").unlink()
        self.commit("remove")
        self.assertIn(merged, {x["commit_sha"] for x in self.scan()["findings"]})

    def test_side_branch_intermediate_secret_is_scanned(self):
        self.git("checkout", "-b", "side")
        introduced = self.add_then_remove()
        self.git("checkout", "main")
        self.commit("main empty")
        self.git("merge", "--no-ff", "-m", "merge side", "side")
        self.assertIn(introduced, {x["commit_sha"] for x in self.scan()["findings"]})

    def test_binary_attribute_cannot_hide_utf8_secret(self):
        (self.repo / ".gitattributes").write_text("*.txt -diff\n", encoding="utf-8")
        self.commit("attributes")
        self.add_then_remove()
        self.assertTrue(self.scan()["findings"])

    def test_external_diff_and_textconv_are_not_executed(self):
        (self.repo / ".gitattributes").write_text("*.txt diff=redactor\n", encoding="utf-8")
        self.git("config", "diff.redactor.textconv", "nonexistent-command-must-not-run")
        self.git("config", "diff.external", "nonexistent-command-must-not-run")
        self.commit("attributes")
        self.add_then_remove()
        self.assertTrue(self.scan()["findings"])

    def test_replacement_objects_do_not_hide_history(self):
        introduced = self.add_then_remove()
        clean = self.git("commit-tree", self.base + "^{tree}", "-p", self.base, "-m", "replacement")
        self.git("replace", introduced, clean)
        self.assertTrue(self.scan()["findings"])

    def test_legacy_grafts_are_rejected(self):
        self.commit("extra")
        path = self.repo / self.git("rev-parse", "--git-path", "info/grafts")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.base + "\n", encoding="ascii")
        with self.assertRaisesRegex(HistoryScanError, "grafts"):
            self.scan()

    def test_commit_limit_fails_instead_of_truncating(self):
        self.commit("one")
        self.commit("two")
        with self.assertRaisesRegex(HistoryScanError, "commit limit"):
            self.scan(max_commits=1)

    def test_byte_limit_fails_instead_of_truncating(self):
        (self.repo / "big.txt").write_text("x" * 200000, encoding="ascii")
        self.commit("large")
        with self.assertRaisesRegex(HistoryScanError, "byte limit"):
            self.scan(max_bytes=1024)

    def test_non_utf8_history_fails_even_after_file_removal(self):
        (self.repo / "binary.dat").write_bytes(b"\xff\xfe\x00")
        self.commit("binary")
        (self.repo / "binary.dat").unlink()
        self.commit("remove")
        with self.assertRaisesRegex(HistoryScanError, "Non-UTF-8"):
            self.scan()

    def test_nul_binary_history_is_not_claimed_as_text_coverage(self):
        (self.repo / "binary.dat").write_bytes(b"\x00plain")
        self.commit("binary")
        with self.assertRaisesRegex(HistoryScanError, "Binary"):
            self.scan()

    def test_submodule_history_requires_separate_review(self):
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",sub")
        self.git("commit", "-m", "gitlink")
        with self.assertRaisesRegex(HistoryScanError, "submodule"):
            self.scan()

    def test_shallow_repository_is_rejected(self):
        self.commit("extra")
        clone = self.root / "shallow"
        self.git("clone", "--depth", "1", self.repo.as_uri(), str(clone))
        with self.assertRaisesRegex(HistoryScanError, "Shallow"):
            scan_history_secrets(worktree=clone, base_sha=self.base,
                                 head_sha=self.git("rev-parse", "HEAD"))

    def test_unrelated_base_is_rejected(self):
        self.git("checkout", "--orphan", "unrelated")
        self.commit("unrelated")
        with self.assertRaises(HistoryScanError):
            self.scan()

    def test_branch_name_instead_of_pinned_sha_is_rejected(self):
        with self.assertRaisesRegex(HistoryScanError, "immutable"):
            scan_history_secrets(worktree=self.repo, base_sha="main", head_sha=self.base)

    def test_git_environment_cannot_redirect_the_scan(self):
        self.add_then_remove()
        with patch.dict(os.environ, {"GIT_DIR": str(self.root / "missing")}):
            result = scan_history_secrets(worktree=self.repo, base_sha=self.base,
                                         head_sha=self.git("rev-parse", "HEAD"))
        self.assertTrue(result["findings"])

    def test_unicode_and_space_paths_still_detect_secrets(self):
        self.add_then_remove(name="中文 notes.txt")
        self.assertTrue(self.scan()["findings"])

    def test_timeout_kills_git_process_without_exporting_output(self):
        real_popen = subprocess.Popen
        processes = []
        def delayed(*args, **kwargs):
            proc = real_popen([sys.executable, "-c", "import time; time.sleep(30)"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            processes.append(proc)
            return proc
        with patch.object(history_scan.subprocess, "Popen", side_effect=delayed):
            with self.assertRaisesRegex(HistoryScanError, "timed out"):
                history_scan._bounded_git(self.repo, ["status"],
                                          deadline=time.monotonic() + 0.05, max_bytes=100)
        self.assertIsNotNone(processes[0].poll())


if __name__ == "__main__":
    unittest.main()
