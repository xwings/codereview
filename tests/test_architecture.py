"""Documentation preflight, preservation, and filesystem boundary regressions."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import architecture
import git_io

READ_FIRST = """Before planning code changes or reviewing code, read
[Agent Rules](ARCHITECTURE/AGENT_RULES.md). Follow the Task Index to the
owning module and read pages whose **Read when** trigger matches the task.
Load partner modules only for affected boundaries; never load the entire
ARCHITECTURE directory. Reuse unchanged pages already read in this session.
Check claims against source, configuration, and tests; they remain
authoritative. If a route or fact is missing or stale, inspect source and
repair the affected docs. For broad changes, work through owners in batches
and retain cross-owner constraints and verification evidence."""

# Minimal, public contract fixture; tests do not depend on an installed skill.

def fixture_skill(version="9.8.7"):
    sections = {name: f"## {name}\n\nCurrent {name} requirements.\n" for name in architecture.SHARED_HEADERS}
    text = (f"---\nmetadata:\n  version: {version}\n---\n\n"
            "## Reading Contract\n\nFollow matching task routes.\n\n"
            "## Version and Freshness Gate\n\nInspect current metadata.\n\n"
            "## Output Contract\n\nSynthetic test contract.\n\n"
            "## Size and Layout\n\nUse kind-specific limits.\n\n"
            "## Root Template\n\n### Read First\n\n```markdown\n" + READ_FIRST + "\n```\n\n"
            "## Agent Rules Template\n\nShared rules live separately.\n\n"
            "## Module Template\n\nUse subsystem owners.\n\n"
            "## Topic and Index Templates\n\nConditional pages and routes.\n\n"
            "## Architecture Verification\n\nVerify routing and evidence.\n\n"
            + "\n".join(sections.values()))
    return architecture.Skill("123456789abcdef", text, sections, version)


ROOT_DOC = """---
eatmycode_version: {version}
---
# Example project Architecture

## Read First

""" + READ_FIRST + """

## Project Snapshot

Return a value for the example command. Python 3 runs without external packages.

## System Design

The command subsystem owns `app.py` and returns a constant value.

## Code Conventions

Use four spaces and the existing simple function style.

## Verification

Inspect the command and run the command owner's Verification steps.

## Task Index

| Source paths / task trigger | Responsibility | Read next |
| --------------------------- | -------------- | --------- |
| `app.py`; change command behavior | Command owner | [Command](ARCHITECTURE/modules/command.md) |
"""
MODULE_DOC = """---
eatmycode_version: {version}
---
# Command

Owner: [Project architecture](../../ARCHITECTURE.md)
Read when: changing `app.py` or command behavior.

## Responsibility and Status

Provide the command entry point. In progress: source inspected; tests not run.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `app.py:4` | Entry point and return value. |

## Local Conventions

Use the [root conventions](../../ARCHITECTURE.md#code-conventions).

## Contracts and Invariants

The function returns one without accepting input or changing state.

## Dependencies and Boundaries

The command owns its complete flow.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Return value changes | The invocation and return value together | Verify the command below. |

## Verification

```sh
python3 app.py
```

Expected exit 0. Not run by this source inspection.

## Known Gaps

Confirm runtime behavior using the command above.
"""
SUPPORT_DOC = """---
eatmycode_version: {version}
---
# Command details

Owner: [Command](../modules/command.md)
Read when: changing the command return value.

## Contract

The entry point at `app.py:4` returns one.

## Change and Verify

Inspect the [owner checks](../modules/command.md#verification).

## Evidence and Gaps

Runtime behavior remains unverified by source inspection.
"""
INDEX_DOC = """---
eatmycode_version: {version}
---
# Command routes

Owner: [Project architecture](../../ARCHITECTURE.md)
Read when: changing `app.py` or command behavior.

## Routes

| Source paths / task trigger | Responsibility | Read next |
| --------------------------- | -------------- | --------- |
| `app.py`; command behavior | Command owner | [Command](../modules/command.md) |
"""


def fixture_documents(skill):
    return {"ARCHITECTURE.md": ROOT_DOC.format(version=skill.version),
            "ARCHITECTURE/modules/command.md": MODULE_DOC.format(version=skill.version),
            architecture.RULES_PATH: architecture._rules_document(skill)}


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clone = Path(self.directory.name).resolve()
        (self.clone / "app.py").write_text("def main():\n    return 1\n\nmain()\n")
        self.skill = fixture_skill()
        self.root_doc = ROOT_DOC.format(version=self.skill.version)
        self.module_doc = MODULE_DOC.format(version=self.skill.version)
        self.support_doc = SUPPORT_DOC.format(version=self.skill.version)
        self.documents = fixture_documents(self.skill)

    def generate(self, documents=None):
        return Mock(return_value={"documents": self.documents if documents is None else documents,
                                  "audited": True, "summary": "Source mapped to command ownership."})

    def test_missing_docs_are_generated_with_latest_blocks_and_entry_symlinks(self):
        self.documents["ARCHITECTURE/modules/command.md"] += "\nRead when: changing return values: [Details](../topics/return.md#contract)\n"
        self.documents["ARCHITECTURE/topics/return.md"] = self.support_doc
        self.documents["ARCHITECTURE.md"] = self.root_doc.replace(
            "ARCHITECTURE/modules/command.md", "ARCHITECTURE/indexes/command.md")
        self.documents["ARCHITECTURE/indexes/command.md"] = INDEX_DOC.format(version=self.skill.version)
        generate = self.generate({name: content for name, content in self.documents.items()
                                  if name != architecture.RULES_PATH})
        report = architecture.prepare(self.clone, self.skill, generate)
        root = (self.clone / "ARCHITECTURE.md").read_text()
        rules = (self.clone / architecture.RULES_PATH).read_text()
        for name, section in self.skill.shared_sections.items():
            self.assertIn(section, rules)
            self.assertNotIn(f"## {name}", root)
        self.assertIn(READ_FIRST, root)
        module = (self.clone / "ARCHITECTURE/modules/command.md").read_text()
        for content in report.documents.values():
            self.assertEqual(architecture._version(content), tuple(map(int, self.skill.version.split("."))))
        self.assertEqual([line for line in root.splitlines() if line.startswith("## ")], [
            "## Read First", "## Project Snapshot", "## System Design", "## Code Conventions",
            "## Verification", "## Task Index",
        ])
        self.assertEqual([line for line in module.splitlines() if line.startswith("## ")], [
            "## Responsibility and Status", "## Code Map", "## Local Conventions",
            "## Contracts and Invariants", "## Dependencies and Boundaries", "## Change Guide",
            "## Verification", "## Known Gaps",
        ])
        self.assertEqual(architecture.SOURCE_REF.findall(module), [("app.py", "4", "")])
        for name in architecture.AGENT_FILES:
            self.assertEqual(os.readlink(self.clone / name), "ARCHITECTURE.md")
        self.assertIn("ARCHITECTURE/modules/command.md", report.changed_paths)
        self.assertIn("ARCHITECTURE/topics/return.md", report.changed_paths)
        self.assertIn(architecture.RULES_PATH, report.changed_paths)
        self.assertEqual((self.clone / "ARCHITECTURE/topics/return.md").read_text(), self.support_doc)
        self.assertIn(str(self.clone), generate.call_args.args[0])
        self.assertIn("NOT executed", report.context())
        self.assertEqual(report.context().count(root), 1)
        self.assertEqual(report.context().count(rules), 1)
        self.assertNotIn(self.support_doc, report.context())
        self.assertNotIn("ARCHITECTURE/topics/return.md", report.context())

        alternate = dict(report.documents)
        alternate["ARCHITECTURE/modules/command.md"] = self.documents["ARCHITECTURE/modules/command.md"].replace(
            "app.py:4", "app.py").replace("```sh\npython3 app.py\n```", "[Root checks](../../ARCHITECTURE.md#verification)")
        architecture.validate_documents(self.clone, alternate, self.skill)
        with tempfile.TemporaryDirectory() as empty:
            empty_docs = {"ARCHITECTURE.md": self.root_doc.replace(
                "| `app.py`; change command behavior | Command owner | [Command](ARCHITECTURE/modules/command.md) |",
                "Unimplemented: no subsystem exists yet."), architecture.RULES_PATH: rules}
            architecture.validate_documents(Path(empty), empty_docs, self.skill)

        updated = fixture_skill("9.10.0")
        sections = dict(updated.shared_sections)
        sections["Review Checks"] += "New upstream requirement.\n"
        updated = architecture.Skill(updated.revision, updated.text, sections, updated.version)
        documents = {name: content.replace(self.skill.version, updated.version, 1)
                     for name, content in self.documents.items() if name != architecture.RULES_PATH}
        generate = self.generate(documents)
        refreshed = architecture.prepare(self.clone, updated, generate)
        generate.assert_called_once()
        self.assertIn("New upstream requirement.", refreshed.documents[architecture.RULES_PATH])
        for name, content in refreshed.documents.items():
            self.assertEqual(architecture._version(content), tuple(map(int, updated.version.split("."))))
            self.assertEqual((self.clone / name).read_text(), content)

    def test_current_set_skips_preparation_and_stale_documents_require_repair(self):
        topic = "ARCHITECTURE/topics/return.md"
        index = "ARCHITECTURE/indexes/command.md"
        self.documents["ARCHITECTURE/modules/command.md"] += "\nRead when: changing return values: [Details](../topics/return.md)\n"
        self.documents[topic] = self.support_doc
        self.documents["ARCHITECTURE.md"] = self.root_doc.replace(
            "ARCHITECTURE/modules/command.md", index)
        self.documents[index] = INDEX_DOC.format(version=self.skill.version)
        architecture.prepare(self.clone, self.skill, self.generate())
        root = self.documents["ARCHITECTURE.md"]
        cases = [
            ("current", "ARCHITECTURE.md", root, False),
            ("shared-rules", architecture.RULES_PATH,
             self.documents[architecture.RULES_PATH].replace("Current Review Checks", "Old Review Checks"), True),
            ("root-header", "ARCHITECTURE.md", root.replace("## Project Snapshot", "## Purpose"), True),
            ("root-index", "ARCHITECTURE.md", root.replace(f"[Command]({index})", "Command"), True),
            ("root-link", "ARCHITECTURE.md", root + "\n[Missing](missing.md)\n", True),
            ("root-reference", "ARCHITECTURE.md", root + "\n`app.py:999`\n", False),
            ("regular-guidance", "AGENTS.md", "Preserve this guidance.\n", False),
            ("missing-entry-link", "AGENTS.md", None, False),
            ("legacy-layout", "ARCHITECTURE/legacy.md", self.module_doc, True),
        ]
        for name, original in self.documents.items():
            for version in ("missing", None, "invalid", "1.0.0", f"{self.skill.version}-rc.1"):
                content = (None if version == "missing" else
                           original.split("---\n", 2)[-1] if version is None else
                           original.replace(self.skill.version, version, 1))
                cases.append((f"{name}-{version}", name, content, True))
            kind = "root" if name == "ARCHITECTURE.md" else "rules" if name == architecture.RULES_PATH else name.split("/")[1]
            limit = architecture.DOCUMENT_LIMITS[kind]
            for size in (limit, limit + 1):
                content = original.replace("\n", "\r\n")
                content += "界" * (size - len(content))
                cases.append((f"{name}-{size}", name, content, size > limit))
        for cause, name, content, audit in cases:
            active = self.skill
            if name == architecture.RULES_PATH and cause.endswith("-12000"):
                # Rules remain verbatim even in the Unicode size boundary cases.
                size = int(cause.rsplit("-", 1)[1])
                sections = dict(self.skill.shared_sections)
                sections["Review Checks"] = sections["Review Checks"].rstrip() + "界" * (
                    size - len(self.documents[architecture.RULES_PATH])) + "\n"
                active = architecture.Skill(self.skill.revision, self.skill.text, sections, self.skill.version)
                content = architecture._rules_document(active)
                self.assertEqual(len(content), size)
            for path, original in self.documents.items():
                (self.clone / path).write_bytes(original.encode())
            legacy = self.clone / "ARCHITECTURE/legacy.md"
            legacy.unlink(missing_ok=True)
            entry = self.clone / "AGENTS.md"
            entry.unlink(missing_ok=True)
            entry.symlink_to("ARCHITECTURE.md")
            path = self.clone / name
            path.unlink(missing_ok=True)
            if content is not None:
                path.write_bytes(content.encode())
            before = {p.relative_to(self.clone): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in self.clone.rglob("*") if p.is_file() and not p.is_symlink()}
            links = {p.name: os.readlink(p) for p in self.clone.iterdir() if p.is_symlink()}
            proposals = dict(self.documents)
            if legacy.exists():
                proposals["ARCHITECTURE/legacy.md"] = None
            generate = self.generate(proposals)
            with self.subTest(cause=cause):
                report = architecture.prepare(self.clone, active, generate)
                self.assertEqual(generate.call_count, int(audit))
                self.assertEqual(report.audited, audit)
                if audit:
                    self.assertEqual(report.documents[topic], self.support_doc)
                else:
                    self.assertEqual(report.changed_paths, ())
                    self.assertEqual(set(report.documents), set(self.documents))
                    self.assertIn("source audit", report.context())
                    self.assertIn("skipped", report.context())
                    self.assertEqual(before, {
                        p.relative_to(self.clone): (p.read_bytes(), p.stat().st_mtime_ns)
                        for p in self.clone.rglob("*") if p.is_file() and not p.is_symlink()
                    })
                    self.assertEqual(links, {p.name: os.readlink(p) for p in self.clone.iterdir() if p.is_symlink()})
                self.assertIn("source", report.context())
                self.assertIn("NOT executed", report.context())
        # A partial repair cannot certify a retained stale page or change any files.
        (self.clone / topic).write_text(self.support_doc.replace(self.skill.version, "1.0.0"))
        before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                  if p.is_file() and not p.is_symlink()}
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate({"ARCHITECTURE.md": root}))
        self.assertEqual(before, {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                                  if p.is_file() and not p.is_symlink()})

    def test_agent_guidance_survives_migration_and_later_root_rewrites(self):
        guidance = ("Use the stable API.\nDeployment: contact the operator before rollout.\n"
                    "Old note `missing.py:999` and [old](gone.md).\n```\nexample\n```\n")
        (self.clone / "AGENTS.md").write_text(guidance)
        original_root = "# Old architecture\n\nDeployment notes for the old command.\n"
        original_module = "# Old module\n\nRetired operational instructions.\n"
        (self.clone / "ARCHITECTURE.md").write_text(original_root)
        (self.clone / "ARCHITECTURE").mkdir()
        (self.clone / "ARCHITECTURE/command.md").write_text(original_module)
        architecture.prepare(self.clone, self.skill, self.generate(self.documents | {"ARCHITECTURE/command.md": None}))
        archive = self.clone / "ARCHITECTURE-ARCHIVE.md"
        previous_archive = archive.read_bytes()
        for original in (guidance, original_root, original_module):
            self.assertIn(original.encode(), previous_archive)
            self.assertNotIn(original, (self.clone / "ARCHITECTURE.md").read_text())
        self.assertNotIn("Deployment:", (self.clone / "ARCHITECTURE.md").read_text())
        self.assertEqual(os.readlink(self.clone / "AGENTS.md"), "ARCHITECTURE.md")
        root_path = self.clone / "ARCHITECTURE.md"
        root_path.write_text(root_path.read_text().replace(self.skill.version, "1.0.0", 1))
        previous_root = root_path.read_bytes()
        previous_module = (self.clone / "ARCHITECTURE/modules/command.md").read_bytes()
        revised = {
            "ARCHITECTURE.md": self.root_doc.replace("example command", "documented command"),
            "ARCHITECTURE/modules/command.md": self.module_doc.replace("returns one", "returns the integer one"),
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
            "root-header": {"ARCHITECTURE.md": self.root_doc.replace("## Project Snapshot", "## Purpose")},
            "root-order": {"ARCHITECTURE.md": self.root_doc.replace("## Read First", "## TEMP")
                           .replace("## System Design", "## Read First")
                           .replace("## TEMP", "## System Design")},
            "header": {"ARCHITECTURE/modules/command.md": self.module_doc.replace("## Responsibility and Status", "## State")},
            "module-order": {"ARCHITECTURE/modules/command.md": self.module_doc.replace("## Code Map", "## TEMP")
                             .replace("## Responsibility and Status", "## Code Map").replace("## TEMP", "## Responsibility and Status")},
            "reference": {"ARCHITECTURE/modules/command.md": self.module_doc.replace("app.py:4", "app.py:999")},
            "index": {"ARCHITECTURE.md": self.root_doc.replace("ARCHITECTURE/modules/command.md", "ARCHITECTURE/missing.md")},
            "link": {"ARCHITECTURE.md": self.root_doc + "\n[escape](../../outside)\n"},
            "null-root": {"ARCHITECTURE.md": None},
            "null-new": {"ARCHITECTURE/missing.md": None},
            "null-path": {"../../escaped.md": None},
            "direct-archive": {"ARCHITECTURE-ARCHIVE.md": "Replace preserved originals."},
            "nested-traversal": {"ARCHITECTURE/details/../../escape.md": "bad"},
            "anchor": {"ARCHITECTURE/modules/command.md": self.module_doc + "\n[Missing](command.md#absent)\n"},
            "unreachable-support": {"ARCHITECTURE/topics/return.md": self.support_doc},
            "support-owner": {"ARCHITECTURE/modules/command.md": self.module_doc + "\nRead when: changing return values: [Details](../topics/return.md)\n",
                              "ARCHITECTURE/topics/return.md": self.support_doc.replace("Owner: [Command](../modules/command.md)", "")},
        }
        module_path = "ARCHITECTURE/modules/command.md"
        topic_path = "ARCHITECTURE/topics/return.md"
        index_path = "ARCHITECTURE/indexes/command.md"
        index_doc = INDEX_DOC.format(version=self.skill.version)
        index_root = self.root_doc.replace(module_path, index_path)
        route = "| `app.py`; command behavior | Command owner | [Command](../modules/command.md) |\n"
        invalid.update({
            "missing-rules": {architecture.RULES_PATH: None},
            "root-read-first": {"ARCHITECTURE.md": self.root_doc.replace("Before planning", "After planning")},
            "copied-root-rules": {"ARCHITECTURE.md": self.root_doc + self.skill.shared_sections["Review Checks"]},
            "legacy-layout": {"ARCHITECTURE/command.md": self.module_doc},
            "uppercase-module": {"ARCHITECTURE/modules/Command.md": self.module_doc},
            "nested-module": {"ARCHITECTURE/modules/nested/command.md": self.module_doc},
            "module-owner": {module_path: self.module_doc.replace("Owner: [Project architecture](../../ARCHITECTURE.md)", "")},
            "module-trigger": {module_path: self.module_doc.replace("Read when: changing `app.py` or command behavior.", "")},
            "topic-trigger": {module_path: self.module_doc + "\nRead when: return changes: [Details](../topics/return.md)\n",
                              topic_path: self.support_doc.replace("Read when: changing the command return value.", "")},
            "topic-headings": {module_path: self.module_doc + "\nRead when: return changes: [Details](../topics/return.md)\n",
                               topic_path: self.support_doc.replace("## Contract", "## Background")},
            "root-route-separator": {"ARCHITECTURE.md": self.root_doc.replace(
                "| --------------------------- | -------------- | --------- |",
                "| `app.py`; command behavior | Command owner | [Command](ARCHITECTURE/modules/command.md) |")},
            "index-route-separator": {"ARCHITECTURE.md": index_root, index_path: index_doc.replace(
                "| --------------------------- | -------------- | --------- |", route.rstrip())},
            "root-route-limit": {"ARCHITECTURE.md": self.root_doc +
                "| `app.py`; command behavior | Command owner | [Command](ARCHITECTURE/modules/command.md) |\n" * 8},
            "index-route-limit": {"ARCHITECTURE.md": index_root, index_path: index_doc + route * 12},
            "index-cycle": {"ARCHITECTURE.md": index_root, index_path: index_doc +
                "| `app.py`; repeat navigation | Invalid self-route | [Again](command.md) |\n"},
        })
        for name, content in self.documents.items():
            kind = "root" if name == "ARCHITECTURE.md" else "rules" if name == architecture.RULES_PATH else name.split("/")[1]
            invalid[f"{name}-size"] = {name: content + "界" * (architecture.DOCUMENT_LIMITS[kind] + 1 - len(content))}
            for version in (None, "1.0.0", f"{self.skill.version}-rc.1", f"{self.skill.version}\neatmycode_version: {self.skill.version}"):
                invalid[f"{name}-stamp-{version}"] = {
                    name: content.split("---\n", 2)[-1]
                    if version is None else content.replace(self.skill.version, version, 1)
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
        previous_root = root_path.read_text().replace(self.skill.version, "1.0.0", 1) + f"\n- [Deployment]({retired_name})\n"
        root_path.write_text(previous_root)
        proposed = {"ARCHITECTURE.md": self.root_doc, retired_name: None}
        before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                  if p.is_file() and not p.is_symlink()}
        for cause in ("audit", "root-link", "module-link"):
            documents = dict(proposed)
            if cause == "root-link":
                documents["ARCHITECTURE.md"] += f"\n- [Deployment]({retired_name})\n"
            elif cause == "module-link":
                documents["ARCHITECTURE/modules/command.md"] = self.module_doc + "\n[Old guide](../deployment.md)\n"
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
        nested = "ARCHITECTURE/topics/return.md"
        (self.clone / nested).parent.mkdir()
        self.documents[nested] = self.support_doc
        self.documents["ARCHITECTURE/legacy.md"] = self.module_doc
        for name in self.documents:
            other = next(path for path in self.documents if path != name)
            for mixed_stale in (False, True):
                for active, future in (("1.1.0", "1.2.0"), ("1.2.0", "1.10.0"),
                                       ("1.1.0", "1.2.0 # verified migration"),
                                       ("1.1.0", '"1.2.0" # verified migration')):
                    for path, content in self.documents.items():
                        version = future if path == name else ("1.0.0" if mixed_stale else active)
                        (self.clone / path).write_text(content.replace(f'"{self.skill.version}"', version, 1).replace(self.skill.version, version, 1)
                                                      + ("x" * 12_001 if mixed_stale and path == other else ""))
                    before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                              if p.is_file() and not p.is_symlink()}
                    skill = architecture.Skill(self.skill.revision, self.skill.text,
                                               self.skill.shared_sections, active)
                    generate = self.generate()
                    with self.subTest(name=name, stale=other if mixed_stale else None,
                                      active=active, future=future):
                        with self.assertRaises(architecture.ArchitectureError):
                            architecture.prepare(self.clone, skill, generate)
                        generate.assert_not_called()
                        self.assertEqual(before, {
                            p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*")
                            if p.is_file() and not p.is_symlink()
                        })

    def test_source_and_output_symlink_escapes_are_rejected(self):
        directory = self.clone / "ARCHITECTURE"
        directory.mkdir()
        (directory / "topics").symlink_to(self.clone.parent)
        (self.clone / "ARCHITECTURE.md").write_text(self.root_doc)
        generate = self.generate()
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, generate)
        generate.assert_not_called()
        with self.assertRaises(architecture.ArchitectureError):
            architecture.validate_documents(self.clone, self.documents | {
                "ARCHITECTURE/topics/return.md": self.support_doc}, self.skill)
        (directory / "topics").unlink()
        (directory / "topics").mkdir()
        (directory / "topics/return.md").symlink_to(self.clone / "app.py")
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, generate)
        (directory / "topics/return.md").unlink()
        (directory / "topics").rmdir()
        directory.rmdir()
        (self.clone / "ARCHITECTURE.md").unlink()
        (self.clone / "ARCHITECTURE").symlink_to(self.clone.parent)
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate())
        (self.clone / "ARCHITECTURE").unlink()
        (self.clone / "escape.py").symlink_to("/etc/passwd")
        docs = self.documents | {"ARCHITECTURE/modules/command.md": self.module_doc.replace("app.py", "escape.py")}
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
        root_path.write_text(root_path.read_text().replace(self.skill.version, "1.0.0", 1))
        with self.assertRaises(architecture.ArchitectureError):
            architecture.prepare(self.clone, self.skill, self.generate({"ARCHITECTURE/retired.md": None}))
        self.assertTrue(retired.is_symlink())
        self.assertEqual((self.clone / "app.py").read_bytes(), original_source)

    def test_apply_rolls_back_every_artifact_on_io_failure(self):
        self.documents["ARCHITECTURE/modules/command.md"] += "\nRead when: changing return values: [Details](../topics/return.md)\n"
        self.documents["ARCHITECTURE/topics/return.md"] = self.support_doc
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
        root_path.write_text(root_path.read_text().replace(self.skill.version, "1.0.0", 1))
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

        documents = {"ARCHITECTURE.md": self.root_doc.replace("example command", "updated command"),
                     "ARCHITECTURE/topics/return.md": self.documents["ARCHITECTURE/topics/return.md"].replace("returns one", "returns the integer one"),
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

    def test_sync_fetches_head_every_time_and_adopts_latest_valid_rules(self):
        cache = self.clone / "eatmycode"
        upstream = self.clone / "upstream"
        upstream.mkdir()
        git_io.git("init", cwd=upstream, isolated=True)
        source = self.skill.text

        def commit(content):
            (upstream / "SKILL.md").write_text(content)
            git_io.git("add", "SKILL.md", cwd=upstream, isolated=True)
            git_io.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                       "commit", "-m", "Update test rules", cwd=upstream, isolated=True)
            return git_io.git("rev-parse", "HEAD", cwd=upstream, isolated=True).stdout.strip()

        revision = commit(source)
        with patch.object(architecture, "UPSTREAM", upstream.as_uri()), \
                patch.object(git_io, "git", wraps=git_io.git) as calls:
            skill = architecture.sync_skill(cache)
            self.assertEqual(skill.revision, revision)
            self.assertEqual(skill.version, self.skill.version)
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

            changed_contract = changed_shared.replace("Synthetic test contract.", "Updated contract.").replace(self.skill.version, "9.10.0")
            latest_revision = commit(changed_contract)
            latest = architecture.sync_skill(cache)
            self.assertEqual((latest.version, latest.revision, latest.text), ("9.10.0", latest_revision, changed_contract))
            for invalid in (changed_contract.replace("9.10.0", "invalid"),
                            changed_contract.replace("metadata:", "unrelated:"),
                            changed_contract.replace("## Coding Discipline", "## Absent"),
                            changed_contract.replace("## Size and Layout", "## Missing Layout"),
                            changed_contract.replace("```markdown", "```text")):
                commit(invalid)
                with self.assertRaises(architecture.ArchitectureError):
                    architecture.sync_skill(cache)


if __name__ == "__main__":
    unittest.main()
