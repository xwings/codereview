"""Documentation preflight, preservation, and filesystem boundary regressions."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import architecture
import git_io

ROOT_DOC = """# Example project

## Purpose

Return a value for the example command.

## Roadmap

M1: document the command and verify its behavior.

## Index

- [Command](ARCHITECTURE/command.md)
"""
MODULE_DOC = """# Command

## Goal

Provide the command entry point for M1.

## Status

in progress (M1) — source inspected; test commands have not been run.

## Code Structure

| File | Role |
| ---- | ---- |
| `app.py` | Entry point and return value. |

## Key Types and Entry Points

- `app.py:1` — main.
- `app.py:2` — result.
- `app.py:4` — invocation.

## Interactions

The command owns its complete flow.

## How to Test

```sh
python3 app.py
```

Expected exit 0. Not run by this source inspection.

## Open Gaps / Roadmap

M1: confirm runtime behavior using the command above.
"""


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clone = Path(self.directory.name).resolve()
        (self.clone / "app.py").write_text("def main():\n    return 1\n\nmain()\n")
        sections = {name: f"## {name}\n\nCurrent {name} requirements.\n" for name in architecture.SHARED_HEADERS}
        self.skill = architecture.Skill("123456789abcdef", "Fixture specification.", sections)
        self.documents = {"ARCHITECTURE.md": ROOT_DOC, "ARCHITECTURE/command.md": MODULE_DOC}

    def generate(self, documents=None):
        return Mock(return_value={"documents": self.documents if documents is None else documents,
                                  "audited": True, "summary": "Source mapped to command ownership."})

    def test_missing_docs_are_generated_with_latest_blocks_and_entry_symlinks(self):
        generate = self.generate()
        report = architecture.prepare(self.clone, self.skill, generate)
        root = (self.clone / "ARCHITECTURE.md").read_text()
        for name, section in self.skill.shared_sections.items():
            self.assertIn(section, root)
            self.assertLess(root.index(f"## {name}"), root.index("## Index"))
        for name in architecture.AGENT_FILES:
            self.assertEqual(os.readlink(self.clone / name), "ARCHITECTURE.md")
        self.assertIn("ARCHITECTURE/command.md", report.changed_paths)
        self.assertIn(str(self.clone), generate.call_args.args[0])
        self.assertIn("NOT executed", report.context())

    def test_existing_docs_still_get_a_semantic_audit_and_new_shared_rules(self):
        architecture.prepare(self.clone, self.skill, self.generate())
        sections = dict(self.skill.shared_sections)
        sections["Review Checks"] += "New upstream requirement.\n"
        current = architecture.Skill("new-revision", self.skill.text, sections)
        generate = self.generate({})
        report = architecture.prepare(self.clone, current, generate)
        generate.assert_called_once()
        self.assertIn("New upstream requirement", report.documents["ARCHITECTURE.md"])
        again = architecture.prepare(self.clone, current, self.generate({}))
        self.assertEqual(again.changed_paths, ())

    def test_agent_guidance_survives_migration_and_later_root_rewrites(self):
        guidance = "Use the stable API.\nOld note `missing.py:999` and [old](gone.md).\n```\nexample\n```\n"
        (self.clone / "AGENTS.md").write_text(guidance)
        architecture.prepare(self.clone, self.skill, self.generate())
        self.assertIn(guidance, (self.clone / "ARCHITECTURE.md").read_text())
        architecture.prepare(self.clone, self.skill, self.generate({"ARCHITECTURE.md": ROOT_DOC}))
        self.assertIn(guidance, (self.clone / "ARCHITECTURE.md").read_text())

    def test_invalid_proposals_never_write_any_files(self):
        invalid = {
            "output-path": {"../../escaped.md": "bad"},
            "header": {"ARCHITECTURE/command.md": MODULE_DOC.replace("## Status", "## State")},
            "reference": {"ARCHITECTURE/command.md": MODULE_DOC.replace("app.py:4", "app.py:999")},
            "index": {"ARCHITECTURE.md": ROOT_DOC.replace("ARCHITECTURE/command.md", "ARCHITECTURE/missing.md")},
            "link": {"ARCHITECTURE.md": ROOT_DOC + "\n[escape](../../outside)\n"},
        }
        for cause, replacements in invalid.items():
            documents = self.documents | replacements
            with self.subTest(cause=cause), self.assertRaises(architecture.ArchitectureError):
                architecture.prepare(self.clone, self.skill, self.generate(documents))
            self.assertEqual({p.name for p in self.clone.iterdir()}, {"app.py"})
        generate = self.generate()
        generate.return_value["audited"] = False
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, generate)

    def test_source_and_output_symlink_escapes_are_rejected(self):
        (self.clone / "ARCHITECTURE").symlink_to(self.clone.parent)
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate())
        (self.clone / "ARCHITECTURE").unlink()
        (self.clone / "escape.py").symlink_to("/etc/passwd")
        docs = self.documents | {"ARCHITECTURE/command.md": MODULE_DOC.replace("app.py", "escape.py")}
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate(docs))

    def test_apply_rolls_back_every_artifact_on_io_failure(self):
        (self.clone / "AGENT.md").write_text("Keep this rule.\n")
        original_replace = os.replace
        failed = False

        def replace(source, target):
            nonlocal failed
            if Path(target) == self.clone / "AGENT.md" and not failed:
                failed = True
                raise OSError("simulated disk error")
            return original_replace(source, target)

        with patch.object(architecture.os, "replace", side_effect=replace), self.assertRaises(OSError):
            architecture.prepare(self.clone, self.skill, self.generate())
        self.assertEqual((self.clone / "AGENT.md").read_text(), "Keep this rule.\n")
        self.assertFalse((self.clone / "ARCHITECTURE.md").exists())
        self.assertFalse((self.clone / "ARCHITECTURE").exists())
        self.assertFalse(list(self.clone.glob(".architecture-stage-*")))

    def test_sync_fetches_head_every_time_and_refuses_stale_or_unknown_rules(self):
        cache = self.clone / "eatmycode"
        cache.mkdir()
        source = "# Fixture\n\n" + "\n".join(self.skill.shared_sections.values())
        (cache / "SKILL.md").write_text(source)

        def git(*args, **kwargs):
            output = {("remote", "get-url", "origin"): architecture.UPSTREAM,
                      ("rev-parse", "FETCH_HEAD"): "new-head"}.get(args, "")
            return subprocess.CompletedProcess(args, 0, output, "")

        with patch.object(git_io, "git", side_effect=git) as calls:
            with patch.object(architecture, "SUPPORTED_CONTRACT", architecture._contract_hash(source)):
                self.assertEqual(architecture.sync_skill(cache).revision, "new-head")
                architecture.sync_skill(cache)
            self.assertEqual(sum(call.args == ("fetch", "--no-tags", "origin", "HEAD")
                                 for call in calls.call_args_list), 2)
        with patch.object(git_io, "git", side_effect=git), self.assertRaises(architecture.ArchitectureError):
            architecture.sync_skill(cache)
        with patch.object(git_io, "git", side_effect=git):
            with patch.object(git_io, "assert_clone_clean", side_effect=SystemExit("dirty")):
                with self.assertRaises(SystemExit):
                    architecture.sync_skill(cache)


if __name__ == "__main__":
    unittest.main()
