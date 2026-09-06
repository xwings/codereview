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
        "verdict": "approve", "review_body": "This change fixes the documented input handling.",
        "findings": [],
        "checklist": {
        name: {"status": "pass", "note": ("Need: justified — " if name == "fit" else "")
               + "app.py:1 meets the documented contract."} for name in reporting.CHECKS
        },
        "chair_vote": {"vote": "merge", "reason": "All objections resolved against app.py:1."},
    }


class ScriptedProvider(kerness.Provider):
    def __init__(self, replies):
        super().__init__(retries=0, backoff_sec=0)
        self.replies = iter(replies)

    def chat_with_retries(self, model, messages, purpose=""):
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
    replies = []
    for phase in panel_runtime.PHASES[kind]:
        for seat, _ in panel_runtime.PANELS[kind]:
            replies += [f"@{seat}, review your area.", "Read app.py:1 and the architecture; no unresolved concern."
                        + ('\nBALLOT {"vote":"merge","reason":"Objection resolved at app.py:1."}'
                           if phase == "vote" else "")
                        + ('\nDOCS_AUDIT {"accepted":true,"reason":"All source and modules checked."}'
                           if kind == "docs" and phase == "verify" and seat == "DocsVerifier" else "")]
    result = "```json\n" + json.dumps(fields) + "\n```"
    return replies + [result, result]  # private draft, then final verdict rethink


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clone = Path(self.directory.name)
        (self.clone / "app.py").write_text("def main():\n    return 1\n\nmain()\n")
        self.fields = pr_fields()
        self.votes = [{"agent": seat, "vote": "merge", "reason": "No unresolved objection at app.py:1."}
                      for seat in [*(s for s, _ in panel_runtime.PANELS["pr"]), "Chair"]]
        self.pr = {"state": "OPEN", "isDraft": False}

    def build(self, kind, replies, transcript=None):
        builder = {"pr": session_builder.build_pr_session,
                   "issue": session_builder.build_issue_session,
                   "docs": session_builder.build_docs_session}[kind]
        return builder(topic="Inspect this checkout.", clone=self.clone,
                       provider=ScriptedProvider(replies), model="offline-fixture",
                       transcript=transcript, max_turns=None)

    def test_real_sessions_complete_all_panels_and_attribute_votes(self):
        cases = {
            "pr": self.fields,
            "issue": {"classification": "support", "response_body": "The return value is expected.",
                      "evidence": [{"file": "app.py", "line": 2, "note": "Returns one."}],
                      "next_steps": [], "labels": ["question"]},
            "docs": {"documents": {"ARCHITECTURE/retired.md": None},
                     "audited": True, "summary": "Inspected source."},
        }
        for kind, fields in cases.items():
            err = ProgressStream()
            original_chat = ScriptedProvider.chat_with_retries

            def delayed_chat(provider, model, messages, purpose=""):
                self.assertIn("waiting for model response", err.getvalue())
                self.assertTrue(err.flushed.wait(2), "No heartbeat during a blocked model request")
                return original_chat(provider, model, messages, purpose)

            with self.subTest(kind=kind), redirect_stderr(err), redirect_stdout(io.StringIO()) as out, \
                    patch.object(progress, "INTERVAL_SECONDS", 0.01), \
                    patch.object(ScriptedProvider, "chat_with_retries", delayed_chat):
                transcript = self.clone / f"{kind}.txt"
                replies = scripted_replies(kind, fields)
                replies.insert(1, '```tool_calls\n[{"name":"read_file","arguments":{"path":"app.py"}}]\n```')
                result = panel_runtime.run_session(self.build(kind, replies, transcript), kind)
                self.assertEqual(result.fields, fields)
                self.assertEqual(len(result.votes), 8 if kind == "pr" else 0)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("app.py:1", transcript.read_text())
                total = len(panel_runtime.PANELS[kind]) * len(panel_runtime.PHASES[kind])
                self.assertIn(f"specialist turns {total}/{total}", err.getvalue())
                self.assertIn(f"phase {len(panel_runtime.PHASES[kind])}/{len(panel_runtime.PHASES[kind])}", err.getvalue())
                self.assertIn("inspecting evidence", err.getvalue())
                self.assertIn("validating participation and final result", err.getvalue())
                self.assertIn("Done:", err.getvalue())
                self.assertNotIn("Read app.py:1", err.getvalue())
                self.assertNotIn("Still working:", transcript.read_text())
                self.assertFalse((self.clone / "session.json").exists())

    def test_incomplete_or_malformed_results_never_become_a_review(self):
        for replies in (["END_REVIEW", "{}", "{}"],
                        scripted_replies("pr", self.fields)[:-2] + ["No JSON", "No JSON"]):
            with self.subTest(replies=len(replies)), redirect_stderr(io.StringIO()):
                with self.assertRaises(panel_runtime.PanelError):
                    panel_runtime.run_session(self.build("pr", replies), "pr")

    def test_chair_cannot_fill_a_missing_or_forged_specialist_ballot(self):
        with redirect_stderr(io.StringIO()):
            result = panel_runtime.run_session(self.build("pr", scripted_replies("pr", self.fields)), "pr")
        for mutation in ("missing-turn", "chair-sender", "missing-ballot", "bad-ballot", "short-rounds"):
            changed = copy.deepcopy(result)
            turns = [m for m in changed.history if m["msg_type"] == "turn"]
            if mutation == "missing-turn":
                changed.history.remove(turns[-1])
            elif mutation == "chair-sender":
                turns[-1]["sender"] = "Chair"
            elif mutation == "missing-ballot":
                turns[-1]["content"] = "The chair can record my vote."
            elif mutation == "bad-ballot":
                turns[-1]["content"] = 'BALLOT {"vote":"merge","reason":""}'
            else:
                changed.rounds_run -= 1
            with self.subTest(mutation=mutation), self.assertRaises(panel_runtime.PanelError):
                panel_runtime.validate_panel(changed, "pr")

    def test_docs_verifier_can_veto_the_chairs_success_claim(self):
        fields = {"documents": {}, "audited": True, "summary": "Chair claims success."}
        for record in ("INCOMPLETE", 'DOCS_AUDIT {"accepted":false,"reason":"Missing source audit."}',
                       'DOCS_AUDIT {"accepted":1,"reason":"Not a boolean."}'):
            replies = scripted_replies("docs", fields)
            replies[-3] = record
            with self.subTest(record=record), redirect_stderr(io.StringIO()):
                with self.assertRaises(panel_runtime.PanelError):
                    panel_runtime.run_session(self.build("docs", replies), "docs")

    def test_approval_requires_unanimity_complete_checks_need_and_open_pr(self):
        self.assertEqual(reporting.validate_pr(self.fields, self.clone, self.votes, self.pr), ("approve", []))
        for cause in ("dissent", "blocker", "concern", "need", "draft", "closed", "chair"):
            fields, votes, pr = copy.deepcopy((self.fields, self.votes, self.pr))
            if cause == "dissent":
                votes[6]["vote"] = "hold"
            elif cause == "blocker":
                fields["findings"] = [{"severity": "major", "file": "app.py", "line": 2,
                                       "message": "Wrong result", "fix": "Return the computed value."}]
            elif cause == "concern":
                fields["checklist"]["dependencies"]["status"] = "concern"
            elif cause == "need":
                fields["checklist"]["fit"]["note"] = "Need: unclear — missing use case."
            elif cause == "draft":
                pr["isDraft"] = True
            elif cause == "closed":
                pr["state"] = "CLOSED"
            else:
                fields["verdict"] = "comment"
            with self.subTest(cause=cause):
                self.assertEqual(reporting.validate_pr(fields, self.clone, votes, pr)[0], "comment")

    def test_invalid_citations_and_missing_checks_stop_publication(self):
        (self.clone / "escape.py").symlink_to("/etc/passwd")
        for name, line in (("../missing", 1), ("escape.py", 1), ("app.py", 99), ("app.py", True)):
            with self.subTest(name=name, line=line), self.assertRaises(reporting.ReportError):
                reporting.source_location(self.clone, {"file": name, "line": line})
        del self.fields["checklist"]["security"]
        with self.assertRaises(reporting.ReportError):
            reporting.validate_pr(self.fields, self.clone, self.votes, self.pr)

    def test_report_is_ordered_and_distinguishes_hold_from_rejection(self):
        self.votes[6].update(vote="hold", reason="Missing evidence | needs\nfollow-up")
        verdict, reasons = reporting.validate_pr(self.fields, self.clone, self.votes, self.pr)
        report = reporting.render_pr(self.fields, self.clone, self.votes, verdict, reasons, allow_approve=False)
        self.assertTrue(report.startswith("## PR verdict: Hold"))
        self.assertIn("7 merge · 1 hold · 0 reject", report)
        self.assertIn("evidence \\| needs follow-up", report)
        self.assertLess(report.index("### Panel votes"), report.index("## Findings"))
        self.assertEqual(report.count(self.fields["review_body"]), 1)
        self.assertIn("<summary>Seven review checks</summary>", report)
        self.assertEqual(reporting.fence("```\ncode\n```"), "````\n```\ncode\n```\n````")

    def test_issue_answer_requires_evidence_and_renders_concrete_next_steps(self):
        fields = {"classification": "bug", "response_body": "The function returns a fixed value.",
                  "evidence": [{"file": "app.py", "line": 2, "note": "Constant return."}],
                  "next_steps": ["Share the expected return value."], "labels": ["bug"]}
        report = reporting.render_issue(fields, self.clone)
        self.assertIn("`app.py:2`", report)
        self.assertIn("Share the expected return value.", report)
        fields["evidence"] = []
        with self.assertRaises(reporting.ReportError):
            reporting.render_issue(fields, self.clone)
        fields["evidence"] = [{"file": "app.py", "line": 2, "note": "Constant return."}]
        fields["classification"] = "invented"
        with self.assertRaisesRegex(reporting.ReportError, "classification"):
            reporting.render_issue(fields, self.clone)

    def test_compact_channel_keeps_raw_text_out_of_output(self):
        for verbose in (False, True):
            with self.subTest(verbose=verbose), redirect_stdout(io.StringIO()) as out, \
                    redirect_stderr(io.StringIO()) as err:
                transcript = self.clone / f"channel-{verbose}.txt"
                channel = panel_runtime.PanelChannel("pr", transcript, verbose)
                channel.send("Chair", "RAW CHAIR DISCUSSION")
                for _ in range(2):
                    for seat, _ in panel_runtime.PANELS["pr"]:
                        channel.send(seat, "RAW PRIVATE DISCUSSION")
                self.assertEqual(channel.completed, 14)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("Security researcher", err.getvalue())
            self.assertIn("phase 1/5: study repo", err.getvalue())
            self.assertIn("phase 2/5: review pr", err.getvalue())
            self.assertIn("specialist turns 14/35", err.getvalue())
            for raw in ("RAW PRIVATE DISCUSSION", "RAW CHAIR DISCUSSION"):
                self.assertEqual(raw in err.getvalue(), verbose)
                self.assertIn(raw, transcript.read_text())

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

    def test_prepare_docs_skips_all_preparation_for_a_current_root(self):
        args = SimpleNamespace(workdir=self.clone, transcript=None, llm_model="fixture",
                               max_turns=None, verbose=False)
        workspace = self.clone / "guide"
        skill = review.architecture.Skill("abc123", "Specification", {}, "1.1.0")
        documents = {"ARCHITECTURE.md": "Architecture guidance", "ARCHITECTURE/command.md": "Command guidance"}
        for version in ("1.1.0", "missing", None, "invalid", "1.0.0"):
            root = self.clone / "ARCHITECTURE.md"
            root.unlink(missing_ok=True)
            if version != "missing":
                root.write_text("Architecture guidance" if version is None else
                                f"---\neatmycode_version: {version}\n---\nArchitecture guidance")
            audited = version != "1.1.0"
            report = review.architecture.Report(skill.revision, (), documents, "Source inspected.")
            with self.subTest(version=version), ExitStack() as stack:
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
                    self.assertIn("Checking baseline ARCHITECTURE.md version", err.getvalue())
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
                    self.assertEqual(actual_report.documents, {"ARCHITECTURE.md": root.read_text()})
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
        source, guide = self.clone / "source", self.clone / "guide"
        source.mkdir()
        (source / "app.py").write_bytes((self.clone / "app.py").read_bytes())
        actual_prepare_docs = review.prepare_docs
        for kind in ("issue", "pr"):
            for current_root in (False, True):
                events = []
                args = SimpleNamespace(repo="a/b", prompts=None, kind="auto", number=1, api_key="fake",
                                       api_base="https://example.invalid", timeout=1, workdir=self.clone,
                                       branch="release/selected", llm_model="fixture", transcript=None,
                                       max_turns=None, verbose=False, allow_approve=False)
                (source / "ARCHITECTURE.md").write_text(
                    "---\neatmycode_version: 1.1.0\n---\nOriginal guide.\n" if current_root else "Old guide.\n")
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
                        events.append("skill") or review.architecture.Skill("abc123", "Specification", {}, "1.1.0")))
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
                        "next_steps": [], "labels": []}
                    stack.enter_context(patch.object(panel_runtime, "run_session", side_effect=lambda *a:
                        events.append("panel") or SimpleNamespace(fields=fields, votes=self.votes)))
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
        result = SimpleNamespace(fields=fields, votes=self.votes)
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
