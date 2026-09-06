"""Offline behavior checks: real kerness sessions, fake model/GitHub responses."""

import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kerness

import git_io
import github_io
import panel_runtime
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
            "docs": {"documents": {}, "audited": True, "summary": "Inspected source."},
        }
        for kind, fields in cases.items():
            with self.subTest(kind=kind), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()) as out:
                transcript = self.clone / f"{kind}.txt"
                result = panel_runtime.run_session(self.build(kind, scripted_replies(kind, fields), transcript), kind)
                self.assertEqual(result.fields, fields)
                self.assertEqual(len(result.votes), 8 if kind == "pr" else 0)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("app.py:1", transcript.read_text())
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
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            channel = panel_runtime.PanelChannel("pr")
            channel.send("Security", "RAW PRIVATE DISCUSSION")
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Security researcher", err.getvalue())
        self.assertNotIn("RAW PRIVATE DISCUSSION", err.getvalue())

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

    def test_preflight_runs_before_kind_detection_and_issue_uses_original_source(self):
        events = []
        args = SimpleNamespace(repo="a/b", prompts=None, kind="auto", number=1, api_key="fake",
                               api_base="https://example.invalid", timeout=1, workdir=self.clone,
                               base_branch=None)
        source, guide = self.clone / "source", self.clone / "guide"
        with ExitStack() as stack:
            stack.enter_context(redirect_stderr(io.StringIO()))
            for target, value in (
                ("review.parse_args", Mock(return_value=args)),
                ("github_io.ensure_gh_ready", Mock()),
                ("architecture.sync_skill", Mock(side_effect=lambda _: events.append("skill"))),
                ("session_builder.build_provider", Mock()),
                ("git_io.ensure_clone", Mock(return_value=self.clone)),
                ("git_io.assert_clone_clean", Mock()),
                ("review.resolve_base_branch", Mock(return_value="main")),
                ("git_io.reset_to_branch", Mock()),
                ("git_io.review_workspace", Mock(return_value=source)),
                ("review.prepare_docs", Mock(side_effect=lambda *a: (events.append("docs") or guide, "report"))),
                ("github_io.detect_kind", Mock(side_effect=lambda *a: events.append("kind") or "issue")),
            ):
                stack.enter_context(patch(target, value))
            handler = stack.enter_context(patch.object(review, "handle_issue", return_value=0))
            self.assertEqual(review.main(), 0)
        self.assertEqual(events, ["skill", "docs", "kind"])
        self.assertEqual(handler.call_args.args[3:], (source, guide, "report"))

    def test_pr_reaudits_its_head_and_cites_original_documentation(self):
        (self.clone / "ARCHITECTURE.md").write_text("Original PR documentation\n")
        guide = self.clone / "guide"
        guide.mkdir()
        (guide / "ARCHITECTURE.md").write_text("Generated replacement documentation\n")
        pr = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "main",
              "state": "OPEN", "isDraft": False}
        args = SimpleNamespace(repo="a/b", number=1, base_branch=None, workdir=self.clone,
                               llm_model="fixture", transcript=None, max_turns=None,
                               verbose=False, allow_approve=True)
        fields = pr_fields()
        fields["findings"] = [{"severity": "major", "file": "ARCHITECTURE.md", "line": 1,
                               "message": "Incorrect original contract.", "fix": "Describe actual behavior."}]
        result = SimpleNamespace(fields=fields, votes=self.votes)
        docs = SimpleNamespace(revision="abc", context=lambda: "Audited guide")
        with ExitStack() as stack:
            for name in ("reset_to_branch", "checkout_pr", "require_head"):
                stack.enter_context(patch.object(git_io, name))
            stack.enter_context(patch.object(git_io, "pr_diff", return_value="diff of original docs"))
            stack.enter_context(patch.object(git_io, "review_workspace", return_value=self.clone))
            stack.enter_context(patch.object(review, "prepare_docs", return_value=(guide, docs)))
            stack.enter_context(patch.object(review.repo_facts, "collect", return_value="facts"))
            stack.enter_context(patch.object(panel_runtime, "run_session", return_value=result))
            builder = stack.enter_context(patch.object(session_builder, "build_pr_session"))
            fetch = stack.enter_context(patch.object(github_io, "fetch_pr", return_value=pr))
            finish = stack.enter_context(patch.object(review, "finish", return_value=0))
            review.handle_pr(args, None, review.DEFAULT_PROFILE_DIR, self.clone, None)
            self.assertEqual(builder.call_args.kwargs["clone"], self.clone)
            self.assertEqual(builder.call_args.kwargs["documentation"], guide)
            self.assertIn("Original PR documentation", finish.call_args.args[1])
            self.assertNotIn("Generated replacement documentation", finish.call_args.args[1])
            self.assertFalse(finish.call_args.kwargs["approve"])
            fetch.side_effect = [pr, pr | {"headRefOid": "b" * 40}]
            finish.reset_mock()
            with self.assertRaises(SystemExit):
                review.handle_pr(args, None, review.DEFAULT_PROFILE_DIR, self.clone, None)
            finish.assert_not_called()

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
        args = Mock(llm_model="fixture", kind="pr", number=1, dry_run=True)
        with patch.object(github_io, "post_pr_review") as post, redirect_stdout(io.StringIO()) as out:
            with redirect_stderr(io.StringIO()):
                review.finish(args, "## Report", "abcdef", approve=True)
        post.assert_not_called()
        self.assertTrue(out.getvalue().startswith("## Report"))

    def test_existing_cli_contracts_and_no_write_commands(self):
        options = ["--repo", "a/b", "--api-key", "fake", "--llm-model", "fixture"]
        for selector, expected in ((["--id", "42"], ("auto", 42)),
                                   (["pr", "42"], ("pr", 42)),
                                   (["issue", "42"], ("issue", 42)),
                                   (["auto", "42"], ("auto", 42))):
            with self.subTest(selector=selector), patch("sys.argv", ["review.py", *selector, *options]):
                args = review.parse_args()
                self.assertEqual((args.kind, args.number), expected)
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
        with patch.object(github_io, "fetch_default_branch", return_value="main") as lookup:
            self.assertEqual(review.resolve_base_branch("a/b", self.clone, "explicit", "release"), "explicit")
            self.assertEqual(review.resolve_base_branch("a/b", self.clone, None, "release"), "release")
            lookup.assert_not_called()
            self.assertEqual(review.resolve_base_branch("a/b", self.clone, None, None), "main")


if __name__ == "__main__":
    unittest.main()
