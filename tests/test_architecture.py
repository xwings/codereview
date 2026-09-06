"""Documentation preflight, preservation, and filesystem boundary regressions."""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import architecture
import git_io

ROOT_DOC = """---
eatmycode_version: 1.1.0
---
# Example project

## Mission and Constraints

Return a value for the example command.

## Languages and Toolchain

Python 3 runs the command without external packages.

## System Design

The command subsystem owns `app.py`.

## Runtime and Data Flow

The interpreter invokes main and returns a constant value.

## Workspace Map

`app.py` contains the command. Its owner is listed in the Index.

## Coding Style and Code Design

Use four spaces and the existing simple function style.

## Verification and Review Map

Inspect the command and run the command owner's How to Test steps.

## Roadmap

M1: document the command and verify its behavior.

## Index

- [Command](ARCHITECTURE/command.md)
"""
MODULE_DOC = """---
eatmycode_version: 1.1.0
---
# Command

## Goal

Provide the command entry point for M1.

## Status

in progress (M1) — source inspected; test commands have not been run.

## Code Structure

| File | Role |
| ---- | ---- |
| `app.py` | Entry point and return value. |

## Language and Conventions

Use the root's Python toolchain and four-space indentation.

## Design and Invariants

The function returns one without accepting input or changing state.

## Key Types and Entry Points

- `app.py:4` — invocation.

## Interactions

The command owns its complete flow.

## How to Test

```sh
python3 app.py
```

Expected exit 0. Not run by this source inspection.

## Review and Refactor Guide

Inspect the invocation and return value together when changing the command.

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
        self.skill = architecture.Skill("123456789abcdef", "Fixture specification.", sections, "1.1.0")
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
        module = (self.clone / "ARCHITECTURE/command.md").read_text()
        for content in (root, module):
            self.assertTrue(content.startswith("---\neatmycode_version: 1.1.0\n---\n"))
        self.assertEqual([line for line in root.splitlines() if line.startswith("## ")], [
            "## Mission and Constraints", "## Languages and Toolchain", "## System Design",
            "## Runtime and Data Flow", "## Workspace Map", "## Coding Style and Code Design",
            "## Verification and Review Map", "## Roadmap", "## Development Loop",
            "## Coding Discipline", "## Review Checks", "## Index",
        ])
        self.assertEqual([line for line in module.splitlines() if line.startswith("## ")], [
            "## Goal", "## Status", "## Code Structure", "## Language and Conventions",
            "## Design and Invariants", "## Key Types and Entry Points", "## Interactions",
            "## How to Test", "## Review and Refactor Guide", "## Open Gaps / Roadmap",
        ])
        self.assertEqual(architecture.SOURCE_REF.findall(module), [("app.py", "4", "")])
        for name in architecture.AGENT_FILES:
            self.assertEqual(os.readlink(self.clone / name), "ARCHITECTURE.md")
        self.assertIn("ARCHITECTURE/command.md", report.changed_paths)
        self.assertIn(str(self.clone), generate.call_args.args[0])
        self.assertIn("NOT executed", report.context())

    def test_current_root_skips_preparation_and_stale_root_requires_repair(self):
        architecture.prepare(self.clone, self.skill, self.generate())
        root = (self.clone / "ARCHITECTURE.md").read_text()
        sections = dict(self.skill.shared_sections)
        sections["Review Checks"] += "New upstream requirement.\n"
        current = architecture.Skill("new-revision", self.skill.text, sections, "1.1.0")
        cases = (
            ("shared-rules", "ARCHITECTURE.md", root),
            ("root-header", "ARCHITECTURE.md", root.replace("## Mission and Constraints", "## Purpose")),
            ("root-index", "ARCHITECTURE.md", root.replace("- [Command](ARCHITECTURE/command.md)", "")),
            ("root-link", "ARCHITECTURE.md", root + "\n[Missing](missing.md)\n"),
            ("root-reference", "ARCHITECTURE.md", root + "\n`app.py:999`\n"),
            ("module-missing", "ARCHITECTURE/command.md", None),
            ("module-old", "ARCHITECTURE/command.md", MODULE_DOC.replace("1.1.0", "1.0.0")),
            ("module-newer", "ARCHITECTURE/command.md", MODULE_DOC.replace("1.1.0", "1.2.0")),
            ("module-malformed", "ARCHITECTURE/command.md", "Unstructured module.\n"),
            ("regular-guidance", "AGENTS.md", "Preserve this guidance.\n"),
            ("missing-entry-link", "AGENTS.md", None),
        )
        for cause, name, content in cases:
            (self.clone / "ARCHITECTURE.md").write_text(root)
            (self.clone / "ARCHITECTURE/command.md").write_text(MODULE_DOC)
            entry = self.clone / "AGENTS.md"
            entry.unlink(missing_ok=True)
            entry.symlink_to("ARCHITECTURE.md")
            path = self.clone / name
            path.unlink(missing_ok=True)
            if content is not None:
                path.write_text(content)
            before = {p.relative_to(self.clone): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in self.clone.rglob("*") if p.is_file() and not p.is_symlink()}
            links = {p.name: os.readlink(p) for p in self.clone.iterdir() if p.is_symlink()}
            generate = self.generate()
            with self.subTest(cause=cause), \
                    patch.object(architecture, "_existing_documents", side_effect=AssertionError("module inventory")), \
                    patch.object(architecture, "_agent_guidance", side_effect=AssertionError("guidance check")), \
                    patch.object(architecture, "validate_documents", side_effect=AssertionError("structure check")):
                report = architecture.prepare(self.clone, current, generate)
                generate.assert_not_called()
                self.assertFalse(report.audited)
                self.assertEqual(report.changed_paths, ())
                self.assertEqual(report.documents, {"ARCHITECTURE.md": (self.clone / "ARCHITECTURE.md").read_text()})
                self.assertIn("Only the root ARCHITECTURE.md version was checked", report.context())
                self.assertIn("preparation and source audit were skipped", report.context())
                self.assertNotIn("structurally checked", report.context())
                self.assertIn("ARCHITECTURE/ when present", report.context())
                self.assertIn("complete related source", report.context())
                self.assertIn("NOT executed", report.context())
                self.assertEqual(before, {
                    p.relative_to(self.clone): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.clone.rglob("*") if p.is_file() and not p.is_symlink()
                })
                self.assertEqual(links, {p.name: os.readlink(p) for p in self.clone.iterdir() if p.is_symlink()})
                self.assertFalse((self.clone / architecture.ARCHIVE_PATH).exists())
        for version in ("missing", None, "invalid", "1.0.0"):
            path = self.clone / "ARCHITECTURE.md"
            if version == "missing":
                path.unlink()
            else:
                path.write_text(ROOT_DOC.replace("---\neatmycode_version: 1.1.0\n---\n", "", 1)
                                if version is None else ROOT_DOC.replace("1.1.0", version, 1))
            (self.clone / "ARCHITECTURE/command.md").write_text(MODULE_DOC.replace("1.1.0", "1.0.0", 1))
            before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                      if p.is_file() and not p.is_symlink()}
            with self.subTest(version=version):
                with self.assertRaises(architecture.ArchitectureError):
                    architecture.prepare(self.clone, current, self.generate({"ARCHITECTURE.md": ROOT_DOC}))
                self.assertEqual(before, {
                    p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                    if p.is_file() and not p.is_symlink()
                })
                generate = self.generate()
                repaired = architecture.prepare(self.clone, current, generate)
                generate.assert_called_once()
                self.assertTrue(repaired.audited)
                self.assertIn("ARCHITECTURE.md", repaired.changed_paths)
                self.assertIn("ARCHITECTURE/command.md", repaired.changed_paths)
                self.assertIn("New upstream requirement", repaired.documents["ARCHITECTURE.md"])
                self.assertEqual(repaired.documents["ARCHITECTURE/command.md"], MODULE_DOC)

    def test_agent_guidance_survives_migration_and_later_root_rewrites(self):
        guidance = ("Use the stable API.\nDeployment: contact the operator before rollout.\n"
                    "Old note `missing.py:999` and [old](gone.md).\n```\nexample\n```\n")
        (self.clone / "AGENTS.md").write_text(guidance)
        original_root = "# Old architecture\n\nDeployment notes for the old command.\n"
        original_module = "# Old module\n\nRetired operational instructions.\n"
        (self.clone / "ARCHITECTURE.md").write_text(original_root)
        (self.clone / "ARCHITECTURE").mkdir()
        (self.clone / "ARCHITECTURE/command.md").write_text(original_module)
        architecture.prepare(self.clone, self.skill, self.generate())
        archive = self.clone / "ARCHITECTURE-ARCHIVE.md"
        previous_archive = archive.read_bytes()
        for original in (guidance, original_root, original_module):
            self.assertIn(original.encode(), previous_archive)
            self.assertNotIn(original, (self.clone / "ARCHITECTURE.md").read_text())
        self.assertNotIn("Deployment:", (self.clone / "ARCHITECTURE.md").read_text())
        self.assertEqual(os.readlink(self.clone / "AGENTS.md"), "ARCHITECTURE.md")
        root_path = self.clone / "ARCHITECTURE.md"
        root_path.write_text(root_path.read_text().replace("1.1.0", "1.0.0", 1))
        previous_root = root_path.read_bytes()
        previous_module = (self.clone / "ARCHITECTURE/command.md").read_bytes()
        revised = {
            "ARCHITECTURE.md": ROOT_DOC.replace("example command", "documented command"),
            "ARCHITECTURE/command.md": MODULE_DOC.replace("returns one", "returns the integer one"),
        }
        later_guidance = "Keep the documented command stable.\n"
        (self.clone / "AGENTS.md").unlink()
        (self.clone / "AGENTS.md").write_text(later_guidance)
        generate = self.generate(revised)
        architecture.prepare(self.clone, self.skill, generate)
        generate.assert_called_once()
        self.assertIn(later_guidance.encode(), archive.read_bytes())
        self.assertTrue(archive.read_bytes().startswith(previous_archive))
        self.assertIn(previous_root, archive.read_bytes())
        self.assertIn(previous_module, archive.read_bytes())
        for original in (guidance, original_root, original_module):
            self.assertIn(original.encode(), archive.read_bytes())
        final_archive = archive.read_bytes()
        self.assertEqual(architecture.prepare(self.clone, self.skill, self.generate({})).changed_paths, ())
        self.assertEqual(archive.read_bytes(), final_archive)

    def test_invalid_proposals_never_write_any_files(self):
        invalid = {
            "output-path": {"../../escaped.md": "bad"},
            "root-header": {"ARCHITECTURE.md": ROOT_DOC.replace("## Mission and Constraints", "## Purpose")},
            "root-order": {"ARCHITECTURE.md": ROOT_DOC.replace("## Languages and Toolchain", "## TEMP")
                           .replace("## System Design", "## Languages and Toolchain")
                           .replace("## TEMP", "## System Design")},
            "header": {"ARCHITECTURE/command.md": MODULE_DOC.replace("## Status", "## State")},
            "module-order": {"ARCHITECTURE/command.md": MODULE_DOC.replace("## Goal", "## TEMP")
                             .replace("## Status", "## Goal").replace("## TEMP", "## Status")},
            "reference": {"ARCHITECTURE/command.md": MODULE_DOC.replace("app.py:4", "app.py:999")},
            "zero-references": {"ARCHITECTURE/command.md": MODULE_DOC.replace("app.py:4", "app.py")},
            "index": {"ARCHITECTURE.md": ROOT_DOC.replace("ARCHITECTURE/command.md", "ARCHITECTURE/missing.md")},
            "link": {"ARCHITECTURE.md": ROOT_DOC + "\n[escape](../../outside)\n"},
            "null-root": {"ARCHITECTURE.md": None},
            "null-new": {"ARCHITECTURE/missing.md": None},
            "null-path": {"../../escaped.md": None},
            "direct-archive": {"ARCHITECTURE-ARCHIVE.md": "Replace preserved originals."},
        }
        for name, content in self.documents.items():
            for version in (None, "1.0.0", "1.1.0-rc.1", "1.1.0\neatmycode_version: 1.1.0"):
                invalid[f"{name}-stamp-{version}"] = {
                    name: content.replace("---\neatmycode_version: 1.1.0\n---\n", "", 1)
                    if version is None else content.replace("eatmycode_version: 1.1.0",
                                                           f"eatmycode_version: {version}", 1)
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

    def test_obsolete_module_deletion_preserves_originals_and_requires_repaired_links(self):
        architecture.prepare(self.clone, self.skill, self.generate())
        retired_name = "ARCHITECTURE/deployment.md"
        retired = "# Deployment\n\nRetired operational guidance.\n"
        (self.clone / retired_name).write_text(retired)
        root_path = self.clone / "ARCHITECTURE.md"
        previous_root = root_path.read_text().replace("1.1.0", "1.0.0", 1) + f"\n- [Deployment]({retired_name})\n"
        root_path.write_text(previous_root)
        proposed = {"ARCHITECTURE.md": ROOT_DOC, retired_name: None}
        before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                  if p.is_file() and not p.is_symlink()}
        for cause in ("audit", "root-link", "module-link"):
            documents = dict(proposed)
            if cause == "root-link":
                documents["ARCHITECTURE.md"] += f"\n- [Deployment]({retired_name})\n"
            elif cause == "module-link":
                documents["ARCHITECTURE/command.md"] = MODULE_DOC + "\n[Old guide](deployment.md)\n"
            generate = self.generate(documents)
            if cause == "audit":
                generate.return_value["audited"] = False
            with self.subTest(cause=cause), self.assertRaises(architecture.ArchitectureError):
                architecture.prepare(self.clone, self.skill, generate)
            self.assertEqual(before, {
                p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                if p.is_file() and not p.is_symlink()
            })
        report = architecture.prepare(self.clone, self.skill, self.generate(proposed))
        self.assertFalse((self.clone / retired_name).exists())
        self.assertNotIn(retired_name, report.documents)
        self.assertNotIn("Deployment", root_path.read_text())
        self.assertIn(retired_name, report.changed_paths)
        self.assertIn("ARCHITECTURE-ARCHIVE.md", report.changed_paths)
        archive = (self.clone / "ARCHITECTURE-ARCHIVE.md").read_bytes()
        self.assertIn(retired.encode(), archive)
        self.assertIn(previous_root.encode(), archive)
        self.assertEqual(architecture.prepare(self.clone, self.skill, self.generate({})).changed_paths, ())
        self.assertEqual((self.clone / "ARCHITECTURE-ARCHIVE.md").read_bytes(), archive)

    def test_newer_versions_stop_before_generation_without_downgrading_any_document(self):
        architecture.prepare(self.clone, self.skill, self.generate())
        for name in self.documents:
            other = next(path for path in self.documents if path != name)
            for mixed_stale in (False, True):
                for active, future in (("1.1.0", "1.2.0"), ("1.2.0", "1.10.0"),
                                       ("1.1.0", "1.2.0 # verified migration"),
                                       ("1.1.0", '"1.2.0" # verified migration')):
                    for path, content in self.documents.items():
                        version = future if path == name else ("1.0.0" if mixed_stale else active)
                        (self.clone / path).write_text(content.replace("1.1.0", version, 1))
                    before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                              if p.is_file() and not p.is_symlink()}
                    skill = architecture.Skill(self.skill.revision, self.skill.text,
                                               self.skill.shared_sections, active)
                    generate = self.generate()
                    with self.subTest(name=name, stale=other if mixed_stale else None,
                                      active=active, future=future):
                        if name == "ARCHITECTURE.md" or mixed_stale:
                            with self.assertRaises(architecture.ArchitectureError):
                                architecture.prepare(self.clone, skill, generate)
                        else:
                            report = architecture.prepare(self.clone, skill, generate)
                            self.assertFalse(report.audited)
                        generate.assert_not_called()
                        self.assertEqual(before, {
                            p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                            if p.is_file() and not p.is_symlink()
                        })

    def test_source_and_output_symlink_escapes_are_rejected(self):
        (self.clone / "ARCHITECTURE").symlink_to(self.clone.parent)
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate())
        (self.clone / "ARCHITECTURE").unlink()
        (self.clone / "escape.py").symlink_to("/etc/passwd")
        docs = self.documents | {"ARCHITECTURE/command.md": MODULE_DOC.replace("app.py", "escape.py")}
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate(docs))
        original_source = (self.clone / "app.py").read_bytes()
        archive = self.clone / "ARCHITECTURE-ARCHIVE.md"
        archive.symlink_to(self.clone / "app.py")
        (self.clone / "AGENT.md").write_text("Keep original guidance.\n")
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate())
        self.assertEqual((self.clone / "app.py").read_bytes(), original_source)
        self.assertTrue(archive.is_symlink())
        archive.unlink()
        architecture.prepare(self.clone, self.skill, self.generate())
        retired = self.clone / "ARCHITECTURE/retired.md"
        retired.symlink_to(self.clone / "app.py")
        root_path = self.clone / "ARCHITECTURE.md"
        root_path.write_text(root_path.read_text().replace("1.1.0", "1.0.0", 1))
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate({"ARCHITECTURE/retired.md": None}))
        self.assertTrue(retired.is_symlink())
        self.assertEqual((self.clone / "app.py").read_bytes(), original_source)

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
        self.assertFalse((self.clone / "ARCHITECTURE-ARCHIVE.md").exists())
        self.assertFalse(list(self.clone.glob(".architecture-stage-*")))
        architecture.prepare(self.clone, self.skill, self.generate())
        retired_name = "ARCHITECTURE/retired.md"
        (self.clone / retired_name).write_text("# Retired\n\nPreserve this operational guide.\n")
        (self.clone / "CLAUDE.md").unlink()
        (self.clone / "CLAUDE.md").write_text("Keep this later guidance.\n")
        root_path = self.clone / "ARCHITECTURE.md"
        root_path.write_text(root_path.read_text().replace("1.1.0", "1.0.0", 1))
        before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                  if p.is_file() and not p.is_symlink()}
        previous_links = {name: os.readlink(self.clone / name) for name in architecture.AGENT_FILES
                          if (self.clone / name).is_symlink()}
        failed = False

        def replace_after_deletion(source, target):
            nonlocal failed
            if Path(target) == self.clone / "CLAUDE.md" and not failed:
                self.assertFalse((self.clone / retired_name).exists())
                self.assertNotEqual((self.clone / "ARCHITECTURE-ARCHIVE.md").read_bytes(),
                                    before[Path("ARCHITECTURE-ARCHIVE.md")])
                failed = True
                raise OSError("simulated error after archive append and deletion")
            return original_replace(source, target)

        documents = {"ARCHITECTURE.md": ROOT_DOC.replace("example command", "updated command"),
                     retired_name: None}
        with patch.object(architecture.os, "replace", side_effect=replace_after_deletion):
            with self.assertRaises(OSError):
                architecture.prepare(self.clone, self.skill, self.generate(documents))
        self.assertTrue(failed)
        self.assertEqual(before, {
            p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
            if p.is_file() and not p.is_symlink()
        })
        self.assertEqual(previous_links, {
            name: os.readlink(self.clone / name) for name in architecture.AGENT_FILES
            if (self.clone / name).is_symlink()
        })
        self.assertFalse(list(self.clone.glob(".architecture-stage-*")))

    def test_sync_fetches_head_every_time_and_refuses_stale_or_unknown_rules(self):
        cache = self.clone / "eatmycode"
        upstream = self.clone / "upstream"
        upstream.mkdir()
        git_io.git("init", cwd=upstream, isolated=True)
        header = "---\nmetadata:\n  version: 9.8.7\n---\n\n"
        footer = "## Output Contract\n\nSynthetic test contract.\n"
        source = header + "".join(self.skill.shared_sections.values()) + footer
        normalized = header + "".join(
            f"## {name}\n[shared section]\n" for name in self.skill.shared_sections
        ) + footer

        def commit(content):
            (upstream / "SKILL.md").write_text(content)
            git_io.git("add", "SKILL.md", cwd=upstream, isolated=True)
            git_io.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                       "commit", "-m", "Update test rules", cwd=upstream, isolated=True)
            return git_io.git("rev-parse", "HEAD", cwd=upstream, isolated=True).stdout.strip()

        revision = commit(source)
        with patch.object(architecture, "UPSTREAM", upstream.as_uri()), \
                patch.object(architecture, "SUPPORTED_CONTRACT", hashlib.sha256(normalized.encode()).hexdigest()), \
                patch.object(git_io, "git", wraps=git_io.git) as calls:
            skill = architecture.sync_skill(cache)
            self.assertEqual(skill.revision, revision)
            self.assertEqual(skill.version, "9.8.7")
            self.assertEqual(skill.text, source)
            self.assertEqual(skill.shared_sections, self.skill.shared_sections)
            changed_shared = source.replace("## Review Checks\n", "## Review Checks\n\nA new shared rule.\n", 1)
            updated_revision = commit(changed_shared)
            updated = architecture.sync_skill(cache)
            self.assertNotEqual(updated.revision, skill.revision)
            self.assertEqual(updated.revision, updated_revision)
            self.assertEqual(updated.text, changed_shared)
            self.assertIn("A new shared rule.", updated.shared_sections["Review Checks"])
            self.assertEqual(architecture.sync_skill(cache), updated)
            self.assertEqual(sum(call.args == ("fetch", "--no-tags", "origin", "HEAD")
                                 for call in calls.call_args_list), 3)

            cached_skill = cache / "SKILL.md"
            cached_skill.write_text(changed_shared + "\nLocal edit.\n")
            with self.assertRaisesRegex(SystemExit, "uncommitted changes"):
                architecture.sync_skill(cache)
            cached_skill.write_text(changed_shared)

            unavailable = self.clone / "unavailable"
            upstream.rename(unavailable)
            try:
                with self.assertRaisesRegex(SystemExit, "fetch"):
                    architecture.sync_skill(cache)
                self.assertEqual(cached_skill.read_text(), changed_shared)
            finally:
                unavailable.rename(upstream)

            commit(changed_shared.replace("Synthetic test contract.", "Unsupported contract."))
            with self.assertRaisesRegex(architecture.ArchitectureError, "changed its supported contract"):
                architecture.sync_skill(cache)


if __name__ == "__main__":
    unittest.main()
