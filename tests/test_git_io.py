"""Local PR merge snapshots and Git program-execution boundaries."""

import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import git_io


class GitSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.remote = self.root / "remote"
        self.remote.mkdir()
        git_io.git("init", cwd=self.remote, isolated=True)
        (self.remote / "app.py").write_text("\n".join(f"line {number}" for number in range(20)) + "\n")
        (self.remote / ".gitattributes").write_text("*.py filter=fixture merge=fixture\n")
        self.common = self.commit("Common source")
        git_io.git("checkout", "-b", "selected", cwd=self.remote, isolated=True)
        (self.remote / "app.py").write_text((self.remote / "app.py").read_text().replace("line 0\n", "selected 0\n"))
        (self.remote / "selected.txt").write_text("Selected branch only.\n")
        self.base = self.commit("Selected branch")
        git_io.git("checkout", "-b", "proposal", self.common, cwd=self.remote, isolated=True)
        (self.remote / "app.py").write_text((self.remote / "app.py").read_text().replace("line 19\n", "proposal 19\n"))
        (self.remote / "proposal.txt").write_text("PR only.\n")
        self.head = self.commit("Proposed change")
        git_io.git("update-ref", "refs/pull/1/head", self.head, cwd=self.remote, isolated=True)
        git_io.git("clone", "--", str(self.remote), str(self.root / "managed"), isolated=True)
        self.clone = self.root / "managed"
        self.managed_head = git_io.git("rev-parse", "HEAD", cwd=self.clone).stdout
        self.managed_branches = git_io.git("show-ref", "--heads", cwd=self.clone).stdout

    def commit(self, message):
        git_io.git("add", ".", cwd=self.remote, isolated=True)
        git_io.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                   "commit", "-m", message, cwd=self.remote, isolated=True)
        return git_io.git("rev-parse", "HEAD", cwd=self.remote).stdout.strip()

    def test_selected_branch_and_merge_snapshots_preserve_managed_branches(self):
        git_io.git("config", "remote.origin.fetch", "+refs/heads/*:refs/heads/*", cwd=self.clone)
        original_git = git_io.git

        def concurrent_fetch(*args, **kwargs):
            result = original_git(*args, **kwargs)
            if args[0] == "fetch" and args[-1].split(":", 1)[0] == "refs/heads/selected":
                original_git("fetch", "--no-tags", "--no-recurse-submodules", "--refmap=",
                             "origin", "refs/heads/proposal", cwd=self.clone)
            return result

        with patch.object(git_io, "git", side_effect=concurrent_fetch):
            issue = git_io.prepare_source(self.clone, self.root, "selected")
        self.assertEqual((issue.base_revision, issue.revision, issue.diff), (self.base, self.base, ""))
        self.assertTrue((issue.path / "selected.txt").exists())
        self.assertFalse((issue.path / "proposal.txt").exists())
        with patch.object(git_io, "git", side_effect=concurrent_fetch):
            source = git_io.prepare_source(self.clone, self.root, "selected", pr_number=1, pr_head=self.head)
        self.assertEqual(source.base_revision, self.base)
        self.assertNotEqual(source.revision, self.head)
        self.assertTrue((source.path / "selected.txt").exists())
        self.assertTrue((source.path / "proposal.txt").exists())
        self.assertIn("selected 0", (source.path / "app.py").read_text())
        self.assertIn("proposal 19", (source.path / "app.py").read_text())
        self.assertIn("proposal.txt", source.diff)
        self.assertNotIn("diff --git a/selected.txt", source.diff)
        self.assertEqual(git_io.git("rev-list", "--parents", "-1", "HEAD", cwd=source.path).stdout.split(),
                         [source.revision, self.base, self.head])
        self.assertEqual(git_io.git("status", "--porcelain", cwd=source.path, isolated=True).stdout, "")
        again = git_io.prepare_source(self.clone, self.root, "selected", pr_number=1, pr_head=self.head)
        self.assertEqual(again.revision, source.revision)
        guide = git_io.review_workspace(source.path, self.root, "guide")
        git_io.require_head(guide, source.revision)
        (guide / "ARCHITECTURE.md").write_text("Generated guide.\n")
        self.assertFalse((source.path / "ARCHITECTURE.md").exists())
        self.assertEqual(git_io.git("rev-parse", "HEAD", cwd=self.clone).stdout, self.managed_head)
        self.assertEqual(git_io.git("show-ref", "--heads", cwd=self.clone).stdout, self.managed_branches)
        self.assertEqual(git_io.git("for-each-ref", "refs/codereview/", cwd=self.clone).stdout, "")
        self.assertEqual(git_io.git("symbolic-ref", "-q", "HEAD", cwd=source.path, check=False).returncode, 1)

    def test_conflicts_head_races_and_dirty_sources_stop_before_review(self):
        with self.assertRaisesRegex(SystemExit, "PR head changed"):
            git_io.prepare_source(self.clone, self.root, "selected", pr_number=1, pr_head="0" * 40)
        self.assertFalse((self.root / ".reviews").exists())
        git_io.git("checkout", "-b", "conflict", self.common, cwd=self.remote, isolated=True)
        (self.remote / "app.py").write_text((self.remote / "app.py").read_text().replace("line 0\n", "conflicting 0\n"))
        conflict = self.commit("Conflicting PR")
        git_io.git("update-ref", "refs/pull/2/head", conflict, cwd=self.remote, isolated=True)
        with self.assertRaisesRegex(SystemExit, "could not be merged") as error:
            git_io.prepare_source(self.clone, self.root, "selected", pr_number=2, pr_head=conflict)
        retained = list((self.root / ".reviews").glob("managed-pr-2-source-*"))
        self.assertEqual(len(retained), 1)
        self.assertIn(str(retained[0]), str(error.exception))
        self.assertTrue((retained[0] / ".git/MERGE_HEAD").exists())
        self.assertEqual(git_io.git("rev-parse", "HEAD", cwd=self.clone).stdout, self.managed_head)
        self.assertEqual(git_io.git("show-ref", "--heads", cwd=self.clone).stdout, self.managed_branches)
        original = (self.clone / "app.py").read_text()
        (self.clone / "app.py").write_text("Uncommitted source.\n")
        with self.assertRaisesRegex(SystemExit, "uncommitted changes"):
            git_io.prepare_source(self.clone, self.root, "selected", pr_number=1, pr_head=self.head)
        self.assertEqual((self.clone / "app.py").read_text(), "Uncommitted source.\n")
        (self.clone / "app.py").write_text(original)
        for branch in ("", "HEAD", "-bad", "main:other", "../main", "main~1", "@{-1}"):
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                git_io.prepare_source(self.clone, self.root, branch)

    def test_source_and_guide_never_run_configured_git_programs(self):
        marker = self.root / "program-ran"
        script = self.root / "configured-program"
        script.write_text(f"#!/bin/sh\nprintf invoked >> {shlex.quote(str(marker))}\nexit 1\n")
        script.chmod(0o755)
        command = shlex.quote(str(script))
        conditional_clone = self.root / "conditional"
        conditional_global = self.root / "conditional-global.gitconfig"
        conditional_filters = self.root / "conditional-filters.gitconfig"
        for key, value in (("filter.fixture.smudge", command), ("filter.fixture.required", "true")):
            git_io.git("config", "--file", str(conditional_filters), key, value)
        git_io.git("config", "--file", str(conditional_global),
                   f"includeIf.gitdir:{conditional_clone}/.git.path", str(conditional_filters))
        git_io.git("config", "--file", str(conditional_global),
                   f"url.{self.remote.as_uri()}.insteadOf", "https://github.com/example/conditional.git")
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(conditional_global)}):
            self.assertEqual(git_io.ensure_clone(self.root, "example/conditional"), conditional_clone)
        self.assertFalse(marker.exists(), "A filter from conditional clone configuration ran")
        self.assertEqual((conditional_clone / "app.py").read_bytes(), (self.remote / "app.py").read_bytes())
        global_config = self.root / "global.gitconfig"
        global_config.write_text("")
        for key, value in (
            ("core.fsmonitor", str(script)), ("core.hooksPath", str(self.clone / ".git/hooks")),
            ("filter.fixture.clean", command), ("filter.fixture.smudge", command),
            ("filter.fixture.process", command), ("filter.fixture.required", "true"),
            ("merge.fixture.driver", command),
        ):
            git_io.git("config", "--file", str(global_config), key, value)
            git_io.git("config", key, value, cwd=self.clone)
        for name in ("post-checkout", "pre-merge-commit", "post-merge", "post-commit"):
            hook = self.clone / ".git/hooks" / name
            hook.write_text(script.read_text())
            hook.chmod(0o755)
        os.utime(self.clone / "app.py", None)
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(global_config)}):
            git_io.assert_clone_clean(self.clone)
            source = git_io.prepare_source(self.clone, self.root, "selected", pr_number=1, pr_head=self.head)
            guide = git_io.review_workspace(source.path, self.root, "guide")
            self.assertEqual((guide / "app.py").read_bytes(), (source.path / "app.py").read_bytes())
            self.assertIn("selected 0", (source.path / "app.py").read_text())
            self.assertIn("proposal 19", (source.path / "app.py").read_text())
        self.assertFalse(marker.exists(), "A hook, filter, merge driver or fsmonitor program ran")
        git_io.git("update-index", "--add", "--cacheinfo", "160000", self.head, "nested", cwd=source.path)
        git_io.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                   "commit", "-m", "Uninitialized gitlink", cwd=source.path, isolated=True)
        nested = source.path / "nested"
        nested.mkdir(exist_ok=True)
        git_io.assert_clone_clean(source.path)
        (nested / ".git").write_text("gitdir: ../.git\n")
        with self.assertRaisesRegex(SystemExit, "initialized submodule"):
            git_io.assert_clone_clean(source.path)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
