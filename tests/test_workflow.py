"""Offline behavior checks: real kerness sessions, fake model/GitHub responses."""

import copy
import io
import json
import subprocess
import tempfile
import threading
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kerness

import git_io
import github_io
import panel_runtime
import progress
import reporting
import review
import session_builder


def pr_fields():
    return {
        "recommendation": "merge", "reason": "No unresolved objection at app.py:1.",
        "review_body": "This change fixes the documented input handling.", "findings": [], "questions": [],
        "checklist": {
            name: {"status": "pass", "note": ("Need: justified — " if name == "fit" else "")
                   + "app.py:1 meets the documented contract."} for name in reporting.CHECKS
        },
    }


def issue_fields(classification="support"):
    return {"classification": classification, "response_body": "The return value is expected.",
            "evidence": [{"file": "app.py", "line": 2, "note": "Returns one."}],
            "next_steps": [], "labels": ["question"], "questions": []}


def record(fields):
    return "RESULT " + json.dumps(fields)


class ScriptedProvider(kerness.Provider):
    def __init__(self, replies):
        super().__init__(retries=0, backoff_sec=0)
        self.replies = iter(replies)
        self.calls = []

    def chat_with_retries(self, model, messages, purpose=""):
        self.calls.append(copy.deepcopy(messages))
        return kerness.ProviderResponse(content=next(self.replies), model=model)

    def chat(self, model, messages):
        return self.chat_with_retries(model, messages)


class ProgressStream(io.StringIO):
    def __init__(self):
        super().__init__()
        self.heartbeat = threading.Event()
        self.flushed = threading.Event()

    def write(self, text):
        count = super().write(text)
        if "Still working:" in text:
            self.heartbeat.set()
        return count

    def flush(self):
        super().flush()
        if self.heartbeat.is_set():
            self.flushed.set()


def scripted_replies(kind, fields):
    if kind == "pr":
        return [record(fields | {"specialists": {}}), record(fields | {"finding_reviews": []})]
    if kind == "issue":
        return [record(fields | {"verify": False})] + (
            [record(fields)] if fields["classification"] not in {"support", "needs_information"} else [])
    replies = []
    for phase in panel_runtime.PHASES["docs"]:
        for seat, _ in panel_runtime.PANELS["docs"]:
            replies += [f"@{seat}, review your area.", "Read app.py:1 and the architecture; no unresolved concern."
                        + ('\nDOCS_AUDIT {"accepted":true,"reason":"All source and modules checked."}'
                           if phase == "verify" and seat == "DocsVerifier" else "")]
    result = "```json\n" + json.dumps(fields) + "\n```"
    return replies + [result, result]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clone = Path(self.directory.name)
        (self.clone / "app.py").write_text("def main():\n    return 1\n\nmain()\n")
        self.fields = pr_fields()
        self.assessments = [{"agent": actor, "recommendation": "merge", "reason": self.fields["reason"]}
                            for actor in ("Lead", "Verifier")]
        self.pr = {"state": "OPEN", "isDraft": False}

    def build(self, kind, replies, transcript=None, **kwargs):
        builder = {"pr": session_builder.build_pr_session,
                   "issue": session_builder.build_issue_session,
                   "docs": session_builder.build_docs_session}[kind]
        self.provider = ScriptedProvider(replies)
        return builder(topic="Inspect this checkout.", clone=self.clone,
                       provider=self.provider, model="offline-fixture",
                       transcript=transcript, **({"max_turns": None} | kwargs))

    def test_real_sessions_complete_required_reviews_and_attribute_assessments(self):
        cases = []
        for names in ([], ["Security"], ["Dependencies"], ["Dependencies", "Security"]):
            lead = self.fields | {"specialists": {name: f"Check {name} at app.py:1." for name in names}}
            consultants = {name: {"findings": [], "questions": [], "summary": f"{name} evidence sentinel app.py:1"}
                           for name in ("Security", "Dependencies") if name in names}
            replies = [record(lead), *(record(value) for value in consultants.values()),
                       record(self.fields | {"finding_reviews": []})]
            cases.append(("pr", replies, ["Lead", *consultants, "Verifier"], self.fields))
        for classification in ("support", "needs_information", "bug", "feature", "documentation", "upstream"):
            for verify in (False, True):
                fields = issue_fields(classification)
                required = verify or classification not in {"support", "needs_information"}
                replies = [record(fields | {"verify": verify}), *([record(fields)] if required else [])]
                cases.append(("issue", replies, ["Investigator", *(["Verifier"] if required else [])],
                              fields | {"verification": "independent" if required else "single_investigation"}))
        docs = {"documents": {"ARCHITECTURE/retired.md": None}, "audited": True, "summary": "Inspected source."}
        cases.append(("docs", scripted_replies("docs", docs),
                      ["DocsPlanner", "DocsWriter", "DocsVerifier"] * 3, docs))
        for index, (kind, replies, actors, fields) in enumerate(cases):
            err = ProgressStream()
            original_chat = ScriptedProvider.chat_with_retries

            def delayed_chat(provider, model, messages, purpose=""):
                self.assertIn("waiting for model response", err.getvalue())
                self.assertTrue(err.flushed.wait(2), "No heartbeat during a blocked model request")
                return original_chat(provider, model, messages, purpose)

            with self.subTest(kind=kind, actors=actors, case=index), redirect_stderr(err), \
                    redirect_stdout(io.StringIO()) as out, patch.object(progress, "INTERVAL_SECONDS", 0.01), \
                    patch.object(ScriptedProvider, "chat_with_retries", delayed_chat):
                transcript = self.clone / f"{kind}-{index}.txt"
                expected_calls = len(replies) + 1
                replies.insert(1 if kind == "docs" else 0,
                               '```tool_calls\n[{"name":"read_file","arguments":{"path":"app.py"}}]\n```')
                result = panel_runtime.run_session(self.build(kind, replies, transcript), kind, clone=self.clone)
                self.assertEqual(result.fields, fields)
                self.assertEqual([m["sender"] for m in result.history if m["msg_type"] == "turn"], actors)
                self.assertEqual(len(self.provider.calls), expected_calls)
                if kind == "pr":
                    self.assertEqual(result.assessments, self.assessments)
                    self.assertEqual(set(result.fields["checklist"]), set(reporting.CHECKS))
                    lead_system = "\n".join(m["content"] for m in self.provider.calls[0] if m["role"] == "system")
                    verifier_system = "\n".join(m["content"] for m in self.provider.calls[-1] if m["role"] == "system")
                    for instructions in (lead_system, verifier_system):
                        self.assertIn("RESULT {JSON}", instructions)
                        self.assertIn("`specialists`", instructions)
                        self.assertIn("`finding_reviews`", instructions)
                    for detail in ("Mixed\n   indentation is major", "comparable definitions and callers",
                                   "distinctive constants, errors, fields and call sequences",
                                   "Trace control flow and failure handling", "benefit relative to API growth",
                                   "license obligations, install-time behavior", "Map affected trust boundaries"):
                        self.assertIn(" ".join(detail.split()), " ".join(lead_system.split()))
                    self.assertIn("A clean initial review still needs", verifier_system)
                    self.assertIn("independently confirm its input, code path", verifier_system)
                    verifier_context = str(self.provider.calls[-1])
                    self.assertIn(lead["review_body"], verifier_context)
                    self.assertIn("Finding catalogue", verifier_context)
                    for actor in actors[1:-1]:
                        self.assertIn(f"{actor} evidence sentinel", verifier_context)
                elif kind == "issue":
                    for call in (self.provider.calls[0], self.provider.calls[-1]):
                        instructions = "\n".join(m["content"] for m in call if m["role"] == "system")
                        self.assertIn("RESULT {JSON}", instructions)
                        self.assertIn("boolean `verify`", instructions)
                if kind != "docs":
                    self.assertEqual(result.end_reason, "host_finished")
                    self.assertNotIn("Chair", actors)
                    self.assertIn(f"step {len(actors)}", err.getvalue())
                else:
                    self.assertIn("specialist turns 9/9", err.getvalue())
                    self.assertIn("phase 3/3", err.getvalue())
                self.assertEqual(out.getvalue(), "")
                self.assertIn("app.py:1" if kind != "issue" else "app.py", transcript.read_text())
                self.assertIn("inspecting evidence", err.getvalue())
                self.assertIn("validating participation and final result", err.getvalue())
                self.assertIn("Done:", err.getvalue())
                self.assertNotIn("Read app.py:1", err.getvalue())
                self.assertNotIn("Still working:", transcript.read_text())
                self.assertFalse((self.clone / "session.json").exists())
                self.assertFalse((self.clone / "memory.md").exists())

        with tempfile.TemporaryDirectory() as directory:
            guide = Path(directory)
            (guide / "ARCHITECTURE.md").write_text("ALLOWED_GUIDE_SENTINEL")
            (guide / "ARCHITECTURE/details").mkdir(parents=True)
            (guide / "ARCHITECTURE/details/return.md").write_text("NESTED_GUIDE_SENTINEL")
            (guide / "private.py").write_text("FORBIDDEN_SOURCE_SENTINEL")
            (self.clone / "escape.py").symlink_to(guide / "private.py")
            attempts = [{"name": "read_file", "arguments": {"path": str(path)}} for path in
                        (guide / "ARCHITECTURE.md", guide / "ARCHITECTURE/details/return.md",
                         guide / "private.py", self.clone / "escape.py")]
            attempts += [{"name": "cmd", "arguments": {"command": "unavailable-command"}},
                         {"name": "write_file", "arguments": {"path": "app.py", "content": "CHANGED"}}]
            replies = ["```tool_calls\n" + json.dumps(attempts) + "\n```", *scripted_replies("pr", self.fields)]
            with redirect_stderr(io.StringIO()):
                panel_runtime.run_session(self.build("pr", replies, documentation=guide), "pr", clone=self.clone)
            context = str(self.provider.calls[1])
            self.assertIn("ALLOWED_GUIDE_SENTINEL", context)
            self.assertIn("NESTED_GUIDE_SENTINEL", context)
            self.assertNotIn("FORBIDDEN_SOURCE_SENTINEL", context)
            self.assertIn("return 1", (self.clone / "app.py").read_text())
            self.assertEqual(context.lower().count("which is outside the workspace"), 2)
            self.assertIn("unknown tool", context.lower())
            (guide / "ARCHITECTURE/details/escape.md").symlink_to(self.clone / "app.py")
            with self.assertRaises(ValueError):
                self.build("pr", [], documentation=guide)

    def test_incomplete_or_malformed_results_never_become_a_review(self):
        lead = self.fields | {"specialists": {}}
        malformed = ["", "END_REVIEW", "RESULT {}", "RESULT []", "RESULT broken",
                     record(lead) + "\n" + record(lead), record(lead) + "\nextra text",
                     record(lead | {"extra": True}), record(lead | {"findings": "none"}),
                     record(lead | {"specialists": {"Chair": "Check it"}}),
                     record(lead | {"specialists": {"Security": ""}})]
        for reply in malformed:
            with self.subTest(reply=reply), redirect_stderr(io.StringIO()), \
                    self.assertRaises((panel_runtime.PanelError, reporting.ReportError)):
                panel_runtime.run_session(self.build("pr", [reply]), "pr", clone=self.clone)
        for kind, fields in (("pr", self.fields), ("issue", issue_fields("bug"))):
            with self.subTest(limit=kind), redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError):
                panel_runtime.run_session(self.build(kind, scripted_replies(kind, fields), max_turns=1),
                                          kind, clone=self.clone)
        for verify in (1, "false", None):
            with self.subTest(verify=verify), redirect_stderr(io.StringIO()), self.assertRaises(reporting.ReportError):
                panel_runtime.run_session(self.build("issue", [record(issue_fields() | {"verify": verify})]),
                                          "issue", clone=self.clone)
        for final in ({}, self.fields | {"finding_reviews": "none"}):
            with self.subTest(final=final), redirect_stderr(io.StringIO()), self.assertRaises(reporting.ReportError):
                panel_runtime.run_session(self.build("pr", [record(lead), record(final)]), "pr", clone=self.clone)
        with redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError):
            panel_runtime.run_session(self.build("docs", ["END_REVIEW", "{}", "{}"]), "docs")
        fake = Mock()
        fake.start.return_value.step.return_value = {"status": "waiting", "reason": {"kind": "approval"}}
        with redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError):
            panel_runtime.run_session(fake, "pr", clone=self.clone)

    def test_final_report_requires_authenticated_independent_results(self):
        with redirect_stderr(io.StringIO()):
            result = panel_runtime.run_session(self.build("pr", scripted_replies("pr", self.fields)),
                                               "pr", clone=self.clone)
        for mutation in ("missing", "duplicate", "reordered", "forged", "unrequested", "count", "end", "fields", "assessment"):
            changed = copy.deepcopy(result)
            turns = [m for m in changed.history if m["msg_type"] == "turn"]
            if mutation == "missing":
                changed.history.remove(turns[-1])
            elif mutation == "duplicate":
                changed.history.append(copy.deepcopy(turns[-1]))
            elif mutation == "reordered":
                turns[0]["sender"], turns[-1]["sender"] = turns[-1]["sender"], turns[0]["sender"]
            elif mutation in ("forged", "unrequested"):
                turns[-1]["sender"] = "Lead" if mutation == "forged" else "Security"
            elif mutation == "count":
                changed.turns_completed -= 1
            elif mutation == "end":
                changed.end_reason = "max_turns"
            elif mutation == "fields":
                changed.fields["review_body"] = "Forged final answer"
            else:
                changed.assessments[-1]["recommendation"] = "hold"
            with self.subTest(mutation=mutation), self.assertRaises(panel_runtime.PanelError):
                panel_runtime.validate_panel(changed, "pr", clone=self.clone)

    def test_docs_verifier_can_veto_the_chairs_success_claim(self):
        fields = {"documents": {}, "audited": True, "summary": "Chair claims success."}
        for record in ("INCOMPLETE", 'DOCS_AUDIT {"accepted":false,"reason":"Missing source audit."}',
                       'DOCS_AUDIT {"accepted":1,"reason":"Not a boolean."}'):
            replies = scripted_replies("docs", fields)
            replies[-3] = record
            with self.subTest(record=record), redirect_stderr(io.StringIO()):
                with self.assertRaises(panel_runtime.PanelError):
                    panel_runtime.run_session(self.build("docs", replies), "docs")

    def test_approval_requires_agreement_complete_checks_need_and_open_pr(self):
        self.assertEqual(reporting.validate_pr(self.fields, self.clone, self.assessments, self.pr), ("approve", []))
        for cause in ("Lead", "Verifier", "blocker", "concern", "style", "naming", "need", "draft", "closed", "question"):
            fields, assessments, pr = copy.deepcopy((self.fields, self.assessments, self.pr))
            if cause in ("Lead", "Verifier"):
                next(a for a in assessments if a["agent"] == cause)["recommendation"] = "hold"
                if cause == "Verifier":
                    fields["recommendation"] = "hold"
            elif cause == "blocker":
                fields["findings"] = [{"severity": "major", "file": "app.py", "line": 2,
                                       "message": "Wrong result", "fix": "Return the computed value."}]
            elif cause in ("concern", "style", "naming"):
                fields["checklist"]["dependencies" if cause == "concern" else cause]["status"] = "concern"
            elif cause == "need":
                fields["checklist"]["fit"]["note"] = "Need: unclear — missing use case."
            elif cause == "draft":
                pr["isDraft"] = True
            elif cause == "closed":
                pr["state"] = "CLOSED"
            else:
                fields["questions"] = ["What is the expected result?"]
            with self.subTest(cause=cause):
                self.assertEqual(reporting.validate_pr(fields, self.clone, assessments, pr)[0], "comment")
        for assessments in ([], self.assessments[:1], self.assessments[:1] * 2,
                            self.assessments[:1] + [self.assessments[1] | {"agent": "Chair"}]):
            with self.subTest(assessments=assessments), self.assertRaises(reporting.ReportError):
                reporting.validate_pr(self.fields, self.clone, assessments, self.pr)

    def test_invalid_citations_and_missing_checks_stop_publication(self):
        (self.clone / "escape.py").symlink_to("/etc/passwd")
        for name, line in (("../missing", 1), ("escape.py", 1), ("app.py", 99), ("app.py", True)):
            with self.subTest(name=name, line=line), self.assertRaises(reporting.ReportError):
                reporting.source_location(self.clone, {"file": name, "line": line})
        for check in reporting.CHECKS:
            fields = copy.deepcopy(self.fields)
            del fields["checklist"][check]
            with self.subTest(check=check), self.assertRaises(reporting.ReportError):
                reporting.validate_pr(fields, self.clone, self.assessments, self.pr)
        candidate = {"severity": "major", "file": "app.py", "line": 2, "message": "Wrong result", "fix": "Compute it."}
        lead = self.fields | {"findings": [candidate], "specialists": {}}
        disposition = {"finding": 1, "status": "withdrawn", "reason": "Documented return.", "file": "app.py", "line": 2}
        for reviews in ([], [disposition, disposition], [disposition | {"finding": 2}],
                        [disposition | {"finding": True}], [disposition | {"line": 99}],
                        [disposition | {"reason": ""}], [disposition | {"status": "ignored"}]):
            with self.subTest(reviews=reviews), self.assertRaises(reporting.ReportError):
                reporting.assemble_pr(lead, {}, self.fields | {"finding_reviews": reviews}, self.clone)

    def test_report_is_ordered_and_distinguishes_hold_from_rejection(self):
        candidate = {"severity": "major", "file": "app.py", "line": 2, "message": "Wrong result", "fix": "Compute it."}
        lead = self.fields | {"recommendation": "hold", "reason": "Missing evidence | needs\nfollow-up",
                              "findings": [candidate], "questions": ["Lead question"],
                              "specialists": {"Security": "Check input."}}
        consultation = {"findings": [candidate | {"message": "Withdraw this"}, candidate | {"message": "Open concern"}],
                        "questions": ["Consultant question"], "summary": "Source checked."}
        reviews = [{"finding": number, "status": status, "reason": "Checked source.", "file": "app.py", "line": 2}
                   for number, status in enumerate(("confirmed", "withdrawn", "unresolved"), 1)]
        verified = self.fields | {"finding_reviews": reviews, "findings": [candidate | {"severity": "nit", "message": "New finding"}]}
        fields, assessments = reporting.assemble_pr(lead, {"Security": consultation}, verified, self.clone)
        self.assertEqual([f["message"] for f in fields["findings"]], ["Wrong result", "New finding"])
        self.assertEqual(fields["questions"][:2], ["Lead question", "Consultant question"])
        self.assertIn("Open concern", fields["questions"][-1])
        verdict, reasons = reporting.validate_pr(fields, self.clone, assessments, self.pr)
        report = reporting.render_pr(fields, self.clone, assessments, verdict, reasons, allow_approve=False)
        self.assertTrue(report.startswith("## PR verdict: Changes requested"))
        self.assertIn(r"evidence \| needs follow-up", report)
        self.assertLess(report.index("### Review assessments"), report.index("## Findings"))
        self.assertEqual(report.count(self.fields["review_body"]), 1)
        self.assertNotIn("Withdraw this", report)
        self.assertIn("Open concern", report)
        self.assertIn("<summary>Seven review checks</summary>", report)
        self.assertIn("| Language conventions | pass |", report)
        self.assertIn("| API naming | pass |", report)
        self.assertEqual(report.count("| Lead |"), 1)
        self.assertEqual(report.count("| Verifier |"), 1)
        self.assertNotIn("Panel votes", report)
        for recommendation, title in (("hold", "Hold"), ("reject", "Do not merge")):
            assessments[0]["recommendation"] = recommendation
            verdict, reasons = reporting.validate_pr(self.fields, self.clone, assessments, self.pr)
            report = reporting.render_pr(self.fields, self.clone, assessments, verdict, reasons, allow_approve=False)
            self.assertTrue(report.startswith(f"## PR verdict: {title}"))
        self.assertEqual(reporting.fence("```\ncode\n```"), "````\n```\ncode\n```\n````")

    def test_issue_answer_requires_evidence_and_renders_concrete_next_steps(self):
        initial = issue_fields("bug") | {"verify": False, "questions": ["Expected result?"]}
        verified = issue_fields("support") | {"response_body": "The fixed value is documented.",
                    "next_steps": ["Share the expected return value."], "questions": ["Which version?"]}
        fields = reporting.assemble_issue(initial, verified, self.clone)
        report = reporting.render_issue(fields, self.clone)
        for text in ("`app.py:2`", "Share the expected return value.", "Expected result?", "Which version?",
                     "The fixed value is documented.", "Independent verification completed."):
            self.assertIn(text, report)
        single = reporting.assemble_issue(issue_fields() | {"verify": False}, None, self.clone)
        self.assertIn("Single investigation", reporting.render_issue(single, self.clone))
        for change in ({"evidence": []}, {"classification": "invented"}, {"verification": "maybe"}):
            with self.subTest(change=change), self.assertRaises(reporting.ReportError):
                reporting.render_issue(fields | change, self.clone)
        with self.assertRaises(reporting.ReportError):
            reporting.assemble_issue(initial, None, self.clone)

    def test_compact_channel_keeps_raw_text_out_of_output(self):
        for verbose in (False, True):
            for kind, actors in (("pr", ["Lead", "Security", "Verifier"]),
                                 ("issue", ["Investigator", "Verifier"]),
                                 ("docs", ["DocsPlanner", "DocsWriter", "DocsVerifier"] * 3)):
                with self.subTest(verbose=verbose, kind=kind), redirect_stdout(io.StringIO()) as out, \
                        redirect_stderr(io.StringIO()) as err:
                    transcript = self.clone / f"channel-{kind}-{verbose}.txt"
                    channel = panel_runtime.PanelChannel(kind, transcript, verbose)
                    channel.send("Chair", "RAW CHAIR DISCUSSION")
                    for actor in actors:
                        channel.send(actor, "RAW PRIVATE DISCUSSION")
                    self.assertEqual(channel.completed, len(actors))
                self.assertEqual(out.getvalue(), "")
                self.assertIn("phase 3/3" if kind == "docs" else f"step {len(actors)}", err.getvalue())
                if kind != "docs":
                    self.assertNotIn("phase", err.getvalue())
                for raw in ("RAW PRIVATE DISCUSSION", "RAW CHAIR DISCUSSION"):
                    self.assertEqual(raw in err.getvalue(), verbose)
                    self.assertIn(raw, transcript.read_text())
        for kind, fields in (("pr", self.fields), ("issue", issue_fields())):
            with self.subTest(transcript_failure=kind), redirect_stderr(io.StringIO()) as err, \
                    patch.object(kerness.FileChannel, "send", side_effect=OSError("Transcript unavailable")):
                with self.assertRaises((OSError, panel_runtime.PanelError)):
                    panel_runtime.run_session(self.build(kind, scripted_replies(kind, fields), self.clone / "failed.txt"),
                                              kind, clone=self.clone)
                self.assertNotIn("Done:", err.getvalue())

    def test_progress_heartbeat_stops_on_success_failure_and_interruption(self):
        for error in (None, ValueError("failed"), SystemExit(2), KeyboardInterrupt()):
            err = ProgressStream()
            with self.subTest(error=type(error).__name__), redirect_stderr(err), \
                    redirect_stdout(io.StringIO()) as out, patch.object(progress, "INTERVAL_SECONDS", 0.01):
                caught = None
                try:
                    with progress.activity("Checking source") as update:
                        self.assertIn("Checking source...", err.getvalue())
                        update("Waiting for repository fetch")
                        self.assertTrue(err.flushed.wait(2), "No flushed heartbeat while work is blocked")
                        self.assertIn("Still working: Waiting for repository fetch", err.getvalue())
                        self.assertIn("elapsed)", err.getvalue())
                        if error is not None:
                            raise error
                except BaseException as exc:
                    caught = exc
                self.assertIs(caught, error)
                self.assertFalse(any(t.name == "review-progress" for t in threading.enumerate()))
                self.assertEqual("Done: Checking source" in err.getvalue(), error is None)
                self.assertEqual(out.getvalue(), "")

    def test_kind_detection_confirms_a_successful_resource_lookup(self):
        def response(code, url="", error="not found"):
            return subprocess.CompletedProcess([], code, json.dumps({"url": url}), error)
        for results, expected in (([response(0)], "pr"),
                                  ([response(1), response(0, "https://github.com/a/b/issues/1")], "issue"),
                                  ([response(1), response(0, "https://github.com/a/b/pull/1")], "pr")):
            with patch.object(github_io, "gh", side_effect=results):
                self.assertEqual(github_io.detect_kind("a/b", 1), expected)
        with patch.object(github_io, "gh", return_value=response(1)), self.assertRaises(SystemExit):
            github_io.detect_kind("a/b", 1)

    def test_prepare_docs_skips_preparation_only_for_a_current_document_set(self):
        args = SimpleNamespace(workdir=self.clone, transcript=None, llm_model="fixture",
                               max_turns=None, verbose=False)
        workspace = self.clone / "guide"
        skill = review.architecture.Skill("abc123", "Synthetic upstream specification", {}, "9.8.7")
        documents = {"ARCHITECTURE.md": "Architecture guidance", "ARCHITECTURE/command.md": "Command guidance"}
        module = self.clone / "ARCHITECTURE/command.md"
        nested = self.clone / "ARCHITECTURE/details/return.md"
        nested.parent.mkdir(parents=True)
        cases = [(version, skill.version, skill.version) for version in (skill.version, "missing", None, "invalid", "1.0.0")]
        cases += [(skill.version, "1.0.0", skill.version), (skill.version, "missing", "missing"),
                  (skill.version, skill.version, "1.0.0"), (skill.version, skill.version, "oversized")]
        for version, module_version, nested_version in cases:
            for path, stamp in ((module, module_version), (nested, nested_version)):
                path.unlink(missing_ok=True)
                if stamp != "missing":
                    content = f"---\neatmycode_version: {stamp if stamp != 'oversized' else skill.version}\n---\nGuidance"
                    path.write_text(content + ("x" * 35_001 if stamp == "oversized" else ""))
            root = self.clone / "ARCHITECTURE.md"
            root.unlink(missing_ok=True)
            if version != "missing":
                root.write_text("Architecture guidance" if version is None else
                                f"---\neatmycode_version: {version}\n---\nArchitecture guidance")
            audited = (version, module_version, nested_version) != (skill.version, skill.version, skill.version)
            report = review.architecture.Report(skill.revision, (), documents, "Source inspected.")
            with self.subTest(versions=(version, module_version, nested_version)), ExitStack() as stack:
                err = stack.enter_context(redirect_stderr(io.StringIO()))
                out = stack.enter_context(redirect_stdout(io.StringIO()))
                worktree = stack.enter_context(patch.object(git_io, "review_workspace", return_value=workspace))
                builder = stack.enter_context(patch.object(session_builder, "build_docs_session"))
                fields = {"documents": {}, "audited": True, "summary": "Source inspected."}
                run = stack.enter_context(patch.object(panel_runtime, "run_session",
                                                      return_value=SimpleNamespace(fields=fields)))

                def prepare(clone, active_skill, generate):
                    self.assertEqual(clone, workspace)
                    self.assertIs(active_skill, skill)
                    self.assertIn("Checking baseline architecture versions and sizes", err.getvalue())
                    self.assertNotIn("Auditing baseline architecture", err.getvalue())
                    self.assertEqual(generate("Audit topic"), fields)
                    return report

                preparation = stack.enter_context(patch.object(review.architecture, "prepare", side_effect=prepare))
                actual_workspace, actual_report = review.prepare_docs(args, None, self.clone, skill, "baseline")
                self.assertEqual(actual_workspace, workspace if audited else self.clone)
                self.assertEqual(actual_report.audited, audited)
                self.assertEqual(worktree.call_count, int(audited))
                self.assertEqual(preparation.call_count, int(audited))
                self.assertEqual(builder.call_count, int(audited))
                self.assertEqual(run.call_count, int(audited))
                if audited:
                    self.assertIs(actual_report, report)
                    worktree.assert_called_once_with(self.clone, args.workdir, "baseline")
                    self.assertEqual(builder.call_args.kwargs["clone"], workspace)
                    self.assertEqual(builder.call_args.kwargs["topic"], "Audit topic")
                    run.assert_called_once_with(builder.return_value, "docs")
                else:
                    self.assertEqual(actual_report.documents, {"ARCHITECTURE.md": root.read_text(),
                        "ARCHITECTURE/command.md": module.read_text(), "ARCHITECTURE/details/return.md": nested.read_text()})
                    self.assertNotIn("documentation workspace", err.getvalue())
                self.assertEqual("Auditing baseline architecture against source" in err.getvalue(), audited)
                self.assertEqual("skipping documentation preparation" in err.getvalue(), not audited)
                self.assertEqual("Validating documentation proposals" in err.getvalue(), audited)
                self.assertEqual(out.getvalue(), "")
                context = review.documentation_context(actual_workspace, actual_report)
                self.assertEqual("source-audited" in context, audited)
                self.assertEqual("preparation and source audit were skipped" in context, not audited)
                self.assertIn("complete related source", context)
                self.assertIn("NOT executed", context)
                self.assertIn("original file and line", context)
                self.assertNotIn("These documents are local guidance, separate", context)

    def test_kind_and_selected_source_precede_one_documentation_gate(self):
        skill = review.architecture.Skill("abc123", "Synthetic upstream specification", {}, "9.8.7")
        source, guide = self.clone / "source", self.clone / "guide"
        source.mkdir()
        (source / "app.py").write_bytes((self.clone / "app.py").read_bytes())
        (source / "ARCHITECTURE").mkdir()
        (source / "ARCHITECTURE/command.md").write_text(f"---\neatmycode_version: {skill.version}\n---\nCommand guide.\n")
        actual_prepare_docs = review.prepare_docs
        for kind in ("issue", "pr"):
            for current_root in (False, True):
                events = []
                args = SimpleNamespace(repo="a/b", prompts=None, kind="auto", number=1, api_key="fake",
                                       api_base="https://example.invalid", timeout=1, workdir=self.clone,
                                       branch="release/selected", llm_model="fixture", transcript=None,
                                       max_turns=None, verbose=False, allow_approve=False)
                (source / "ARCHITECTURE.md").write_text(
                    f"---\neatmycode_version: {skill.version}\n---\nOriginal guide.\n" if current_root else "Old guide.\n")
                snapshot = git_io.Source(source, "b" * 40, "c" * 40, "merged diff" if kind == "pr" else "")
                pr = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "main",
                      "state": "OPEN", "isDraft": False}
                docs = review.architecture.Report("abc123", (), {"ARCHITECTURE.md": "Generated guide."}, "Checked.")

                def prepare_source(clone, workdir, branch, **kwargs):
                    events.append("source")
                    self.assertEqual((clone, workdir, branch), (self.clone, args.workdir, args.branch))
                    self.assertEqual(kwargs, {"pr_number": 1 if kind == "pr" else None,
                                              "pr_head": pr["headRefOid"] if kind == "pr" else None})
                    return snapshot

                def prepare_docs(*arguments):
                    events.append("docs")
                    self.assertEqual(arguments[2], source)
                    self.assertEqual(arguments[4], f"{kind}-1")
                    return actual_prepare_docs(*arguments) if current_root else (guide, docs)

                with self.subTest(kind=kind, current_root=current_root), ExitStack() as stack:
                    err = stack.enter_context(redirect_stderr(io.StringIO()))
                    stack.enter_context(patch.object(review, "parse_args", return_value=args))
                    stack.enter_context(patch.object(github_io, "ensure_gh_ready"))
                    stack.enter_context(patch.object(github_io, "detect_kind",
                                                    side_effect=lambda *a: events.append("kind") or kind))
                    stack.enter_context(patch.object(github_io, "fetch_pr",
                                                    side_effect=lambda *a: events.append("pr") or pr))
                    stack.enter_context(patch.object(github_io, "fetch_issue", return_value={"number": 1}))
                    stack.enter_context(patch.object(git_io, "ensure_clone", return_value=self.clone))
                    stack.enter_context(patch.object(git_io, "assert_clone_clean"))
                    stack.enter_context(patch.object(git_io, "prepare_source", side_effect=prepare_source))
                    stack.enter_context(patch.object(review.architecture, "sync_skill", side_effect=lambda *a:
                        events.append("skill") or skill))
                    stack.enter_context(patch.object(session_builder, "build_provider"))
                    gate = stack.enter_context(patch.object(review, "prepare_docs", side_effect=prepare_docs))
                    preparation = stack.enter_context(patch.object(review.architecture, "prepare"))
                    docs_builder = stack.enter_context(patch.object(session_builder, "build_docs_session"))
                    worktree = stack.enter_context(patch.object(git_io, "review_workspace"))
                    builder = stack.enter_context(patch.object(session_builder, f"build_{kind}_session"))
                    stack.enter_context(patch.object(review.repo_facts, "collect", return_value="Source facts."))
                    fields = self.fields if kind == "pr" else {
                        "classification": "support", "response_body": "The result is expected.",
                        "evidence": [{"file": "app.py", "line": 2, "note": "Returns one."}],
                        "next_steps": [], "labels": [], "questions": [], "verification": "single_investigation"}
                    stack.enter_context(patch.object(panel_runtime, "run_session", side_effect=lambda *a, **k:
                        events.append("panel") or SimpleNamespace(fields=fields, assessments=self.assessments)))
                    finish = stack.enter_context(patch.object(review, "finish",
                                                             side_effect=lambda *a, **k: events.append("answer") or 0))
                    self.assertEqual(review.main(), 0)
                    self.assertEqual(events, ["kind", *(["pr"] if kind == "pr" else []), "source", "skill",
                                              "docs", "panel", *(["pr"] if kind == "pr" else []), "answer"])
                    gate.assert_called_once()
                    preparation.assert_not_called()
                    docs_builder.assert_not_called()
                    worktree.assert_not_called()
                    self.assertEqual(builder.call_args.kwargs["clone"], source)
                    self.assertEqual(builder.call_args.kwargs["documentation"], None if current_root else guide)
                    for text in (args.branch, snapshot.revision):
                        self.assertIn(text, builder.call_args.kwargs["topic"])
                        self.assertIn(text, finish.call_args.args[1])
                    self.assertIn("Original guide." if current_root else "Generated guide.",
                                  builder.call_args.kwargs["topic"])
                    self.assertNotIn(args.api_key, err.getvalue())
                    self.assertNotIn(args.api_base, err.getvalue())
        for failure in ("kind mismatch", "merge conflict", "PR head changed during fetch"):
            args.kind = "pr" if failure == "kind mismatch" else "auto"
            with self.subTest(failure=failure), ExitStack() as stack:
                stack.enter_context(redirect_stderr(io.StringIO()))
                stack.enter_context(patch.object(review, "parse_args", return_value=args))
                stack.enter_context(patch.object(github_io, "ensure_gh_ready"))
                stack.enter_context(patch.object(github_io, "detect_kind",
                                                return_value="issue" if failure == "kind mismatch" else "pr"))
                stack.enter_context(patch.object(github_io, "fetch_pr", return_value=pr))
                clone = stack.enter_context(patch.object(git_io, "ensure_clone", return_value=self.clone))
                stack.enter_context(patch.object(git_io, "assert_clone_clean"))
                stack.enter_context(patch.object(git_io, "prepare_source", side_effect=SystemExit(failure)))
                skill = stack.enter_context(patch.object(review.architecture, "sync_skill"))
                prepare = stack.enter_context(patch.object(review, "prepare_docs"))
                panel = stack.enter_context(patch.object(panel_runtime, "run_session"))
                finish = stack.enter_context(patch.object(review, "finish"))
                with self.assertRaises(SystemExit):
                    review.main()
                if failure == "kind mismatch":
                    clone.assert_not_called()
                for call in (skill, prepare, panel, finish):
                    call.assert_not_called()

    def test_pr_reviews_merged_source_and_rechecks_head_before_publication(self):
        (self.clone / "ARCHITECTURE.md").write_text("Merged source documentation\n")
        guide = self.clone / "guide"
        guide.mkdir()
        (guide / "ARCHITECTURE.md").write_text("Generated replacement documentation\n")
        pr = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "main",
              "state": "OPEN", "isDraft": False}
        args = SimpleNamespace(repo="a/b", number=1, branch="release/selected", workdir=self.clone,
                               llm_model="fixture", transcript=None, max_turns=None,
                               verbose=False, allow_approve=True)
        snapshot = git_io.Source(self.clone, "b" * 40, "c" * 40, "selected branch to local merge")
        fields = pr_fields()
        fields["findings"] = [{"severity": "major", "file": "ARCHITECTURE.md", "line": 1,
                               "message": "Incorrect merged contract.", "fix": "Describe actual behavior."}]
        result = SimpleNamespace(fields=fields, assessments=self.assessments)
        docs = SimpleNamespace(revision="abc", context=lambda: "Prepared guide")
        with ExitStack() as stack:
            err = stack.enter_context(redirect_stderr(io.StringIO()))
            prepare = stack.enter_context(patch.object(review, "prepare_docs"))
            facts = stack.enter_context(patch.object(review.repo_facts, "collect", return_value="facts"))
            stack.enter_context(patch.object(panel_runtime, "run_session", return_value=result))
            builder = stack.enter_context(patch.object(session_builder, "build_pr_session"))
            fetch = stack.enter_context(patch.object(github_io, "fetch_pr", return_value=pr))
            finish = stack.enter_context(patch.object(review, "finish", return_value=0))
            for workspace in (guide, self.clone):
                review.handle_pr(args, None, review.DEFAULT_PROFILE_DIR, pr, snapshot, workspace, docs)
                self.assertEqual(builder.call_args.kwargs["clone"], self.clone)
                self.assertEqual(builder.call_args.kwargs["documentation"], guide if workspace == guide else None)
                facts.assert_called_with(self.clone, snapshot.diff)
                for text in (args.branch, snapshot.base_revision, snapshot.revision, pr["headRefOid"]):
                    self.assertIn(text, builder.call_args.kwargs["topic"])
                    self.assertIn(text, finish.call_args.args[1])
                self.assertIn("Merged source documentation", finish.call_args.args[1])
                self.assertNotIn("Generated replacement documentation", finish.call_args.args[1])
                self.assertFalse(finish.call_args.kwargs["approve"])
            prepare.assert_not_called()
            for key, value in (("headRefOid", "d" * 40), ("baseRefName", "other"),
                               ("state", "CLOSED"), ("isDraft", True)):
                fetch.return_value = pr | {key: value}
                finish.reset_mock()
                err.seek(0)
                err.truncate()
                with self.subTest(changed=key), self.assertRaises(SystemExit):
                    review.handle_pr(args, None, review.DEFAULT_PROFILE_DIR, pr, snapshot, guide, docs)
                finish.assert_not_called()
                self.assertNotIn("Done: Rechecking PR head and state", err.getvalue())

    def test_local_worktree_isolation_dirty_guard_and_head_check(self):
        git_io.git("init", cwd=self.clone)
        git_io.git("add", "app.py", cwd=self.clone)
        git_io.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                   "commit", "-m", "fixture", cwd=self.clone)
        head = git_io.git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()
        git_io.assert_clone_clean(self.clone)
        snapshot = git_io.review_workspace(self.clone, self.clone.parent / "work", "source")
        self.addCleanup(lambda: git_io.git("worktree", "remove", "--force", str(snapshot), cwd=self.clone))
        (snapshot / "ARCHITECTURE.md").write_text("Generated locally\n")
        git_io.assert_clone_clean(self.clone)
        self.assertFalse((self.clone / "ARCHITECTURE.md").exists())
        git_io.require_head(snapshot, head)
        with self.assertRaises(SystemExit):
            git_io.require_head(snapshot, "wrong-head")
        (self.clone / "app.py").write_text("Uncommitted work\n")
        with self.assertRaises(SystemExit):
            git_io.assert_clone_clean(self.clone)

    def test_posting_preserves_literal_markdown_with_body_files(self):
        body = "A `literal` command, $(not-executed), and a newline.\nSecond line.\n"
        captured = []

        def gh(*args):
            captured.append((args, Path(args[-1]).read_text()))

        with patch.object(github_io, "gh", side_effect=gh):
            github_io.post_pr_review("a/b", 1, approve=False, body=body)
            github_io.post_issue_comment("a/b", 1, body)
        self.assertTrue(all(args[-2] == "--body-file" and content == body for args, content in captured))
        self.assertTrue(all(not Path(args[-1]).exists() for args, _ in captured))

    def test_dry_run_prints_only_report_and_never_posts(self):
        for kind in ("pr", "issue"):
            for dry_run in (True, False):
                args = Mock(llm_model="fixture", repo="a/b", kind=kind, number=1, dry_run=dry_run)
                with self.subTest(kind=kind, dry_run=dry_run), \
                        patch.object(github_io, "post_pr_review") as pr_post, \
                        patch.object(github_io, "post_issue_comment") as issue_post, \
                        redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                    def post(*a, **kw):
                        self.assertIn("Posting", err.getvalue())
                        self.assertNotIn("Done:", err.getvalue())
                        self.assertTrue(out.getvalue().startswith("## Report"))
                    pr_post.side_effect = issue_post.side_effect = post
                    review.finish(args, "## Report", "abcdef", approve=True)
                self.assertEqual(pr_post.call_count, int(not dry_run and kind == "pr"))
                self.assertEqual(issue_post.call_count, int(not dry_run and kind == "issue"))
                self.assertTrue(out.getvalue().startswith("## Report"))
                self.assertNotIn("Posting", out.getvalue())
                self.assertIn("Dry run: nothing posted" if dry_run else "Done: Posting", err.getvalue())

    def test_existing_cli_contracts_and_no_write_commands(self):
        options = ["--repo", "a/b", "--api-key", "fake", "--llm-model", "fixture",
                   "--branch", "release/selected"]
        for selector, expected in ((["--id", "42"], ("auto", 42)),
                                   (["pr", "42"], ("pr", 42)),
                                   (["issue", "42"], ("issue", 42)),
                                   (["auto", "42"], ("auto", 42))):
            with self.subTest(selector=selector), patch("sys.argv", ["review.py", *selector, *options]):
                args = review.parse_args()
                self.assertEqual((args.kind, args.number), expected)
                self.assertEqual(args.branch, "release/selected")
        forwarded = ["--id", "42", "--repo", "old/project", "--dry-run",
                     "--api-base", "https://server", *options, "--dry-run"]
        with patch("sys.argv", ["review.py", *forwarded]):
            args = review.parse_args()
            self.assertEqual((args.repo, args.api_base, args.dry_run), ("a/b", "https://server", True))
        for selector in ([], ["--id", "0"], ["--id", "-1"], ["--id", "xxx"], ["--id"],
                         ["pr"], ["pr", "42", "--id", "42"]):
            with self.subTest(selector=selector), patch("sys.argv", ["review.py", *selector, *options]):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    review.parse_args()
                self.assertEqual(error.exception.code, 2)
        for value in ("owner/name", "https://github.com/a/b.git", "git@github.com:a/b.git"):
            self.assertEqual(review.normalize_repo(value).count("/"), 1)
        for value in ("../../etc", "a/b/c", "https://gitlab.com/a/b", "a/.."):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                review.normalize_repo(value)
        for args, forbidden, tool in (
            (("-C", "x", "push"), github_io.FORBIDDEN_GIT_PREFIXES, "git"),
            (("api", "x"), github_io.FORBIDDEN_GH_PREFIXES, "gh"),
            (("pr", "merge", "1"), github_io.FORBIDDEN_GH_PREFIXES, "gh"),
            (("issue", "close", "1"), github_io.FORBIDDEN_GH_PREFIXES, "gh"),
            (("repo", "sync"), github_io.FORBIDDEN_GH_PREFIXES, "gh"),
        ):
            with self.subTest(args=args), self.assertRaises(github_io.ForbiddenCommand):
                github_io._check_prefix(args, forbidden, tool)
        for value in (None, "", "-option", "../main", "a:b", "a*", "two branches", "@{-1}", "HEAD", "main~1"):
            branch_options = [] if value is None else [f"--branch={value}"]
            with self.subTest(branch=value), patch("sys.argv", ["review.py", "--id", "42", *options[:-2], *branch_options]):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    review.parse_args()
                self.assertEqual(error.exception.code, 2)



if __name__ == "__main__":
    unittest.main()
