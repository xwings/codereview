"""Offline behavior checks: real kerness sessions, fake model/GitHub responses."""

import copy
import io
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kerness

import git_io
import github_io
import panel_runtime
import progress
import provider_io
import reporting
import review
import session_builder
from tests.test_architecture import fixture_documents, fixture_skill


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
                self.assertIn(f"request {expected_calls}", err.getvalue())
                self.assertIn("s total)", err.getvalue())
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
                    for instructions in (lead_system, verifier_system):
                        self.assertIn("AGENT_RULES.md", instructions)
                        self.assertIn("Task Index", instructions)
                        self.assertIn("Read when", instructions)
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
                        self.assertIn("AGENT_RULES.md", instructions)
                        self.assertIn("Task Index", instructions)
                if kind != "docs":
                    self.assertEqual(result.end_reason, "host_finished")
                    self.assertNotIn("Chair", actors)
                    for actor in actors:
                        phase = "verify" if actor == "Verifier" else "review"
                        self.assertIn(f"[offline-fixture] [{actor}] [{phase}] waiting for model response", err.getvalue())
                else:
                    for phase in ("plan", "draft", "verify"):
                        for actor in ("Chair", "DocsPlanner", "DocsWriter", "DocsVerifier"):
                            self.assertIn(f"[offline-fixture] [{actor}] [{phase}] waiting for model response", err.getvalue())
                    self.assertEqual(err.getvalue().count("[Chair] [summary] waiting for model response"), 2)
                self.assertEqual(err.getvalue().count("review turn completed"), len(actors))
                for line in err.getvalue().splitlines():
                    self.assertRegex(line, r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[offline-fixture\] \[\w+\] \[\w+\] ")
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
            (guide / "ARCHITECTURE/topics").mkdir(parents=True)
            (guide / "ARCHITECTURE/topics/return.md").write_text("NESTED_GUIDE_SENTINEL")
            (guide / "private.py").write_text("FORBIDDEN_SOURCE_SENTINEL")
            (self.clone / "escape.py").symlink_to(guide / "private.py")
            attempts = [{"name": "read_file", "arguments": {"path": str(path)}} for path in
                        (guide / "ARCHITECTURE.md", guide / "ARCHITECTURE/topics/return.md",
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
            (guide / "ARCHITECTURE/topics/escape.md").symlink_to(self.clone / "app.py")
            with self.assertRaises(ValueError):
                self.build("pr", [], documentation=guide)

        # Documentation planning sees bounded metadata pages, never file bodies.
        directory = self.clone / "ARCHITECTURE/topics"
        directory.mkdir(parents=True)
        for index in range(45):
            (directory / f"part-{index:02d}.md").write_text(
                "---\neatmycode_version: 9.8.7\n---\nINVENTORY_BODY_SENTINEL界\n")
        inventory = next(handler for name, _, _, handler in session_builder.agent_tools.docs_tools(self.clone)
                         if name == "architecture_inventory")
        first = json.loads(inventory({}))
        second = json.loads(inventory({"offset": first["next_offset"]}))
        self.assertEqual((len(first["files"]), len(second["files"])), (40, 5))
        self.assertEqual(first["total_files"], 45)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(len({entry["path"] for entry in first["files"] + second["files"]}), 45)
        self.assertTrue(all(entry["kind"] == "topics" and entry["version"] == "9.8.7"
                            for entry in first["files"] + second["files"]))
        self.assertNotIn("INVENTORY_BODY_SENTINEL", json.dumps(first))
        for invalid in (-1, True, "0"):
            self.assertIn("error:", inventory({"offset": invalid}))
        escaped = directory / "escape.md"
        escaped.symlink_to(self.clone / "app.py")
        self.assertIn("metadata unavailable", inventory({}))
        escaped.unlink()
        for tools in (session_builder.agent_tools.pr_tools(self.clone), session_builder.agent_tools.issue_tools(self.clone)):
            self.assertNotIn("architecture_inventory", [name for name, *_ in tools])
        docs = {"documents": {}, "audited": True, "summary": "Inspected source."}
        replies = scripted_replies("docs", docs)
        replies.insert(1, '```tool_calls\n[{"name":"architecture_inventory","arguments":{}}]\n```')
        with redirect_stderr(io.StringIO()):
            panel_runtime.run_session(self.build("docs", replies), "docs")
        self.assertIn('"next_offset": 40', str(self.provider.calls[2]))
        self.assertNotIn("INVENTORY_BODY_SENTINEL", str(self.provider.calls))

    def test_provider_retries_failures_at_fixed_interval_before_failing_the_panel(self):
        custom_provider = provider_io.ObservedProvider
        errors = [
            (kerness.ProviderNetworkError("PRIVATE_URL", TimeoutError("PRIVATE_CAUSE: timed out")),
             "ProviderNetwork: request timed out"),
            (kerness.ProviderHTTPError(400, "PRIVATE_URL", "PRIVATE_BODY"), "ProviderHttp HTTP 400"),
            ({"choices": [{"message": {"content": ""}}]}, "ProviderEmpty"),
        ]
        scenarios = [(0, None, "")] + [(count, failure, diagnostic)
            for failure, diagnostic in errors for count in (2, 3)]
        docs = {"documents": {}, "audited": True, "summary": "Inspected source."}
        cases = [("pr", self.fields, session_builder.build_pr_session, ["Lead", "Verifier"]),
                 ("issue", issue_fields("bug"), session_builder.build_issue_session,
                  ["Investigator", "Verifier"]),
                 ("docs", docs, session_builder.build_docs_session,
                  ["DocsPlanner", "DocsWriter", "DocsVerifier"] * 3)]
        for kind, fields, builder, actors in cases:
            replies = scripted_replies(kind, fields)
            responses = [{"choices": [{"message": {"content": reply}}], "model": "offline-fixture"}
                         for reply in replies]
            for failures, failure, diagnostic in scenarios:
                with self.subTest(kind=kind, failures=failures, diagnostic=diagnostic), ExitStack() as stack:
                    out = stack.enter_context(redirect_stdout(io.StringIO()))
                    err = stack.enter_context(redirect_stderr(io.StringIO()))
                    # Keep the real provider and retry loop; remove only the waits.
                    factory = stack.enter_context(patch.object(session_builder, "ObservedProvider", side_effect=lambda **kwargs:
                        custom_provider(**(kwargs | {"backoff_sec": 0, "interval_sec": 0}))))
                    post = stack.enter_context(patch("kerness.provider.http_post_json",
                        side_effect=[responses[0], *([failure] * failures), *responses[1:]]))
                    provider = session_builder.build_provider("PRIVATE_KEY", "https://example.invalid", 7)
                    self.assertEqual(factory.call_args.kwargs.get("interval_sec"), 30)
                    session = builder(topic="Inspect this checkout.", clone=self.clone, provider=provider,
                                      model="offline-fixture", transcript=None, max_turns=None)
                    if failures == 3:
                        with self.assertRaisesRegex(panel_runtime.PanelError, diagnostic) as error:
                            panel_runtime.run_session(session, kind, clone=self.clone)
                        self.assertEqual(post.call_count, 4)
                        self.assertNotIn("Done:", err.getvalue())
                        for private in ("PRIVATE_URL", "PRIVATE_CAUSE", "PRIVATE_BODY", "PRIVATE_KEY"):
                            self.assertNotIn(private, str(error.exception))
                    else:
                        result = panel_runtime.run_session(session, kind, clone=self.clone)
                        self.assertEqual(post.call_count, len(replies) + failures)
                        self.assertEqual([m["sender"] for m in result.history if m["msg_type"] == "turn"], actors)
                        self.assertEqual(result.fields, fields | ({"verification": "independent"} if kind == "issue" else {}))
                    self.assertEqual(out.getvalue(), "")
                    self.assertEqual(err.getvalue().count("payload JSON="), post.call_count)
                    if failures:
                        self.assertIn("request 2, attempt 2/3 (retry 1/2)", err.getvalue())
                        self.assertIn("request 2, attempt 3/3 (retry 2/2)", err.getvalue())
                    for private in ("PRIVATE_URL", "PRIVATE_CAUSE", "PRIVATE_BODY", "PRIVATE_KEY"):
                        self.assertNotIn(private, err.getvalue())
                    self.assertTrue(all(call.kwargs["timeout"] == 7 for call in post.call_args_list))
                    if failures:
                        self.assertTrue(all(call == post.call_args_list[1] for call in post.call_args_list[1:4]))
                    self.assertIs(kerness.provider.http_post_json, post)
                    if failures and isinstance(failure, Exception):
                        self.assertIn("retry 1/2 in 30s", err.getvalue())
                        self.assertIn("retry 2/2 in 30s", err.getvalue())

        # Compatibility fallbacks keep the logical request and reset its retry sequence.
        for refusals in (("tools",), ("reasoning_effort",), ("tools", "reasoning_effort")):
            responses = [{"choices": [{"message": {"content": reply}}]}
                         for reply in scripted_replies("pr", self.fields)]
            failures = [kerness.ProviderHTTPError(400, "PRIVATE_URL", f"PRIVATE_BODY: unsupported {name}")
                        for name in refusals for _ in range(3)]
            with self.subTest(fallbacks=refusals), redirect_stderr(io.StringIO()) as err, \
                    patch("kerness.provider.http_post_json", side_effect=[*failures, *responses]) as post:
                provider = custom_provider(url="https://example.invalid", api_key="PRIVATE_KEY",
                                           retries=2, interval_sec=0, backoff_sec=0)
                session = session_builder.build_pr_session(topic="Inspect this checkout.", clone=self.clone,
                    provider=provider, model="offline-fixture", transcript=None, max_turns=None)
                result = panel_runtime.run_session(session, "pr", clone=self.clone)
                self.assertEqual(result.fields, self.fields)
                self.assertEqual(post.call_count, len(failures) + len(responses))
                for sequence in range(1, len(refusals) + 1):
                    self.assertIn(f"request 1, fallback {sequence}, attempt 1/3 (initial)", err.getvalue())
                self.assertIn("request 2, attempt 1/3 (initial)", err.getvalue())
                self.assertNotIn("request 3", err.getvalue())
                payload = post.call_args_list[-1].args[1]
                for name in refusals:
                    self.assertNotIn(name, payload)
                self.assertIs(kerness.provider.http_post_json, post)
                for private in ("PRIVATE_URL", "PRIVATE_BODY", "PRIVATE_KEY"):
                    self.assertNotIn(private, err.getvalue())

    def test_provider_measures_assembled_prompts_and_reports_usage_without_content(self):
        # Exercise the native schema and tool-result payloads, not a parallel prompt builder.
        secret = "PRIVATE_PROMPT_你好_🙂"
        (self.clone / "app.py").write_text("def main():\n    return 1\n# " + secret + "\n")
        tool_reply = {"choices": [{"message": {"content": "", "tool_calls": [{
            "id": "read1", "type": "function", "function": {
                "name": "read_file", "arguments": json.dumps({"path": str(self.clone / "app.py")}),
            },
        }]}}]}
        final_reply = {"choices": [{"message": {"content": scripted_replies("issue", issue_fields())[0]}}]}
        for usage, expected in (({"prompt_tokens": 123}, 123), ({"input_tokens": 456}, 456),
                                ({"prompt_tokens": True}, None), ({"prompt_tokens": -1}, None),
                                ({"prompt_tokens": "PRIVATE_USAGE"}, None), ({}, None)):
            with self.subTest(usage=usage), redirect_stderr(io.StringIO()) as err, \
                    redirect_stdout(io.StringIO()) as out, patch("kerness.provider.http_post_json",
                        side_effect=[tool_reply, final_reply | {"usage": usage}]) as post:
                provider = session_builder.build_provider("PRIVATE_KEY", "https://example.invalid", 7)
                transcript = self.clone / "measured.txt"
                session = session_builder.build_issue_session(topic=secret, clone=self.clone, provider=provider,
                    model="offline-fixture", transcript=transcript, max_turns=None)
                panel_runtime.run_session(session, "issue", clone=self.clone)
                self.assertEqual(post.call_count, 2)
                metrics = [line for line in err.getvalue().splitlines() if "payload JSON=" in line]
                self.assertEqual(len(metrics), 2)
                sizes = []
                for call, line in zip(post.call_args_list, metrics):
                    payload = call.args[1]
                    serialized = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    messages, tools = serialized(payload["messages"]), serialized(payload["tools"])
                    chars = len(messages) + len(tools)
                    sizes.append(len(messages.encode("utf-8")))
                    self.assertIn(f"{len(payload['messages'])} messages; {chars} prompt JSON chars", line)
                    self.assertIn(f"(~{chars // 4} tokens, chars/4 estimate)", line)
                    self.assertIn(f"messages JSON={sizes[-1]} B", line)
                    self.assertIn(f"{len(payload['tools'])} tool schemas JSON={len(tools.encode('utf-8'))} B", line)
                    self.assertIn(f"payload JSON={len(serialized(payload).encode('utf-8'))} B", line)
                    self.assertGreater(sizes[-1], len(messages))
                    for role in ("system", "user", "assistant", "tool"):
                        size = sum(len(serialized(message).encode("utf-8")) for message in payload["messages"]
                                   if message["role"] == role)
                        if size:
                            self.assertIn(f"{role}={size}", line)
                self.assertGreater(sizes[1], sizes[0])
                self.assertTrue(any(message["role"] == "tool" and secret in message["content"]
                                    for message in post.call_args.args[1]["messages"]))
                self.assertEqual("provider input tokens=" in err.getvalue(), expected is not None)
                if expected is not None:
                    self.assertIn(f"provider input tokens={expected}", err.getvalue())
                for private in (secret, "PRIVATE_KEY", "PRIVATE_USAGE", "https://example.invalid"):
                    self.assertNotIn(private, err.getvalue())
                self.assertEqual(out.getvalue(), "")
                self.assertNotIn("payload JSON=", transcript.read_text())
                self.assertNotIn("provider input tokens=", transcript.read_text())
                self.assertIs(kerness.provider.http_post_json, post)

    def test_provider_observation_scopes_compaction_and_unrelated_threads(self):
        messages = [{"role": "user", "content": "PRIVATE_MESSAGE"}]
        response = {"choices": [{"message": {"content": "Fixture response."}}]}
        plain = kerness.CustomProvider(url="https://example.invalid", api_key="PRIVATE_KEY", retries=0)
        observed = session_builder.build_provider("PRIVATE_KEY", "https://example.invalid", 7)
        failures = []

        def unrelated():
            try:
                plain.chat_with_retries("unrelated", messages)
            except BaseException as exc:
                failures.append(exc)

        def transport(url, payload, headers, *, timeout):
            if payload["model"] == "observed":
                worker = threading.Thread(target=unrelated)
                worker.start()
                worker.join(2)
                self.assertFalse(worker.is_alive(), "Observer blocked an unrelated provider")
            return response

        with redirect_stderr(io.StringIO()) as err, \
                patch("kerness.provider.http_post_json", side_effect=transport) as post:
            models = {"Lead": "observed", "Chair": "summary", "Verifier": "observed"}
            with progress.activity("Panel") as update, provider_io.observe_requests(update, models, "Chair") as panel:
                panel.started("Lead", "review")
                observed.chat_with_retries("observed", messages)
                self.assertIs(kerness.provider.http_post_json, post)
                observed.chat_with_retries("summary", messages, purpose="compaction")
                panel.started("Verifier", "verify")
                observed.chat_with_retries("observed", messages)
                self.assertEqual(panel.number, 3)
            self.assertFalse(failures)
            self.assertEqual(post.call_count, 5)
            self.assertEqual(err.getvalue().count("payload JSON="), 3)
            self.assertIn("[summary] [Chair] [compact] request 2, attempt 1/3", err.getvalue())
            self.assertIn("[observed] [Verifier] [verify] request 3, attempt 1/3", err.getvalue())
            self.assertNotIn("unrelated", err.getvalue())
            self.assertNotIn("PRIVATE_MESSAGE", err.getvalue())
            self.assertIs(kerness.provider.http_post_json, post)
            logged = err.getvalue()
            observed.chat_with_retries("outside-panel", messages)
            self.assertEqual(err.getvalue(), logged)

        for marker in ("waiting for model response", "payload JSON=", "HTTP response received"):
            error = OSError("stderr unavailable")

            def broken_output(message, **context):
                if marker in message:
                    raise error

            with self.subTest(broken_output=marker), \
                    patch("kerness.provider.http_post_json", return_value=response) as post, \
                    patch.object(provider_io, "emit", side_effect=broken_output), \
                    provider_io.observe_requests(lambda *a, **k: None, {"Lead": "observed"}, "Lead") as panel:
                panel.started("Lead", "review")
                panel.update = broken_output
                with self.assertRaises(OSError) as caught:
                    observed.chat_with_retries("observed", messages)
                self.assertIs(caught.exception, error)
                self.assertEqual(post.call_count, 1, "Failed telemetry retried a successful model call")
                self.assertIs(kerness.provider.http_post_json, post)

    def test_format_corrections_preserve_history_and_required_reviewers(self):
        lead = self.fields | {"specialists": {name: f"Check {name}." for name in ("Security", "Dependencies")}}
        consultant = {"findings": [], "questions": [], "summary": "Checked app.py:1."}
        cases = [
            ("pr", [lead, consultant, consultant, self.fields | {"finding_reviews": []}],
             ["Lead", "Security", "Dependencies", "Verifier"], self.fields),
            ("issue", [issue_fields("bug") | {"verify": True}, issue_fields("bug")],
             ["Investigator", "Verifier"], issue_fields("bug") | {"verification": "independent"}),
        ]
        for kind, stages, actors, expected in cases:
            with self.subTest(kind=kind):
                invalid = ["Unformatted response sentinel", record(stages[1]) + "\nextra text",
                           "RESULT {", "RESULT broken"]
                corrected = ["RESULT\n" + json.dumps(stage, indent=2) for stage in stages]
                replies = [reply for index, response in enumerate(corrected) for reply in (invalid[index], response)]
                transcript = self.clone / f"corrected-{kind}.txt"
                with redirect_stderr(io.StringIO()) as err, redirect_stdout(io.StringIO()) as out:
                    result = panel_runtime.run_session(self.build(kind, replies, transcript), kind, clone=self.clone)
                turns = [message for message in result.history if message["msg_type"] == "turn"]
                self.assertEqual([message["sender"] for message in turns], [actor for actor in actors for _ in range(2)])
                self.assertEqual([message["content"] for message in turns], replies)
                self.assertEqual(result.turns_completed, len(replies))
                self.assertEqual(len(self.provider.calls), len(replies))
                self.assertEqual(result.fields, expected)
                self.assertEqual(result.assessments, self.assessments if kind == "pr" else [])
                for call in self.provider.calls[1::2]:
                    self.assertIn("Correct only the result format", call[-1]["content"])
                    self.assertIn("RESULT", call[-1]["content"])
                self.assertIn("requesting one result-format correction", err.getvalue())
                self.assertNotIn(invalid[0], err.getvalue())
                self.assertIn(invalid[0], transcript.read_text())
                self.assertEqual(out.getvalue(), "")

                for mutation in ("missing correction", "different actor", "third attempt", "valid duplicate"):
                    changed = copy.deepcopy(result)
                    history = changed.history
                    first = next(i for i, message in enumerate(history) if message["msg_type"] == "turn")
                    correction = next(i for i in range(first + 1, len(history)) if history[i]["msg_type"] == "turn")
                    if mutation == "missing correction":
                        history.pop(correction)
                        changed.turns_completed -= 1
                    elif mutation == "different actor":
                        history[correction]["sender"] = actors[1]
                    elif mutation == "third attempt":
                        history.insert(first, copy.deepcopy(history[first]))
                        changed.turns_completed += 1
                    else:
                        history[first]["content"] = history[correction]["content"]
                    with self.subTest(kind=kind, mutation=mutation), self.assertRaises(panel_runtime.PanelError):
                        panel_runtime.validate_panel(changed, kind, clone=self.clone)

    def test_incomplete_or_malformed_results_never_become_a_review(self):
        for kind, fields in (("pr", self.fields), ("issue", issue_fields()),
                             ("docs", {"documents": {}, "audited": True, "summary": "Checked."})):
            for replies in (scripted_replies(kind, fields),
                            ['```tool_calls\n[{"name":"read_file","arguments":{"path":"app.py"}}]\n```']):
                session = self.build(kind, replies)
                original_chat = self.provider.chat_with_retries

                def delayed_chat(*args, **kwargs):
                    if len(self.provider.calls) == len(replies) - 1:
                        time.sleep(0.2)
                    return original_chat(*args, **kwargs)

                with self.subTest(elapsed=kind, replies=replies), redirect_stderr(io.StringIO()) as err, \
                        redirect_stdout(io.StringIO()) as out, \
                        patch.object(self.provider, "chat_with_retries", delayed_chat), \
                        self.assertRaisesRegex(panel_runtime.PanelError, "panel time budget exhausted"):
                    panel_runtime.run_session(session, kind, clone=self.clone, timeout_s=0.1)
                self.assertEqual(len(self.provider.calls), len(replies))
                self.assertNotIn("inspecting evidence", err.getvalue())
                self.assertNotIn("Done:", err.getvalue())
                self.assertEqual(out.getvalue(), "")
        lead = self.fields | {"specialists": {}}
        malformed = ["", "END_REVIEW", "RESULT {}", "RESULT []", "RESULT broken",
                     record(lead) + "\n" + record(lead), record(lead) + "\nextra text",
                     json.dumps(lead) + "\n" + json.dumps(lead),
                     "```json\n" + json.dumps(lead), "```json\n" + json.dumps(lead) + "\n~~~",
                     "```json\n" + record(lead), "```json\n" + record(lead) + "\n~~~",
                     "```json\n" + json.dumps(lead) + "\n```\nextra text",
                     "An example: " + json.dumps(lead),
                     "```json\n" + record(lead) + "\n" + record(lead) + "\n```",
                     "```json\n" + json.dumps(lead | {"findings": [{"severity": "major", "file": "app.py",
                         "line": 99, "message": "Wrong result", "fix": "Compute it."}]}) + "\n```",
                     record(lead | {"extra": True}), record(lead | {"findings": "none"}),
                     record(lead | {"specialists": {"Chair": "Check it"}}),
                     record(lead | {"specialists": {"Security": ""}})]
        for reply in malformed:
            with self.subTest(reply=reply), redirect_stderr(io.StringIO()), \
                    self.assertRaises((panel_runtime.PanelError, reporting.ReportError)):
                panel_runtime.run_session(self.build("pr", [reply, reply]), "pr", clone=self.clone)
        for kind in ("pr", "issue"):
            for limit in (None, 1):
                with self.subTest(correction=kind, limit=limit), redirect_stderr(io.StringIO()), \
                        self.assertRaises(panel_runtime.PanelError) as error:
                    panel_runtime.run_session(self.build(kind, ["Unformatted response sentinel"] * 2,
                                                         max_turns=limit), kind, clone=self.clone)
                self.assertEqual(len(self.provider.calls), 2 if limit is None else 1)
                self.assertNotIn("Unformatted response sentinel", str(error.exception))
                if limit is None:
                    self.assertIn("Result-format correction failed", str(error.exception))
                    self.assertIn("no complete review result", str(error.exception))
                    self.assertNotIn("re-run with --verbose", str(error.exception))
        for kind, fields in (("pr", self.fields), ("issue", issue_fields("bug"))):
            with self.subTest(limit=kind), redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError):
                panel_runtime.run_session(self.build(kind, scripted_replies(kind, fields), max_turns=1),
                                          kind, clone=self.clone)
        for verify in (1, "false", None):
            with self.subTest(verify=verify), redirect_stderr(io.StringIO()), self.assertRaises(reporting.ReportError):
                panel_runtime.run_session(self.build("issue", [record(issue_fields() | {"verify": verify})]),
                                          "issue", clone=self.clone)
            self.assertEqual(len(self.provider.calls), 1)
        for final in ({}, self.fields | {"finding_reviews": "none"}):
            with self.subTest(final=final), redirect_stderr(io.StringIO()), self.assertRaises(reporting.ReportError):
                panel_runtime.run_session(self.build("pr", [record(lead), record(final)]), "pr", clone=self.clone)
            self.assertEqual(len(self.provider.calls), 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError):
            panel_runtime.run_session(self.build("docs", ["END_REVIEW", "{}", "{}"]), "docs")
        fake = Mock()
        fake._agents = []
        fake.start.return_value.step.return_value = {"status": "waiting", "reason": {"kind": "approval"}}
        with redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError):
            panel_runtime.run_session(fake, "pr", clone=self.clone)
        failures = [
            ({"ProviderHttp": {"status_code": 429, "url": "PRIVATE_URL", "body": "RAW PROVIDER RESPONSE"}},
             "failed (ProviderHttp HTTP 429)"),
            ({"ProviderNetwork": {"url": "PRIVATE_URL", "cause": "PRIVATE_CAUSE: timed out reading response"}},
             "failed (ProviderNetwork: request timed out)"),
            (None, "invalid_result (max_turns)"),
        ]
        for failure, expected in failures:
            fake.start.return_value.step.return_value = {
                "status": "finished", "outcome": {
                    "reason": {"kind": "failed" if failure else "invalid_result"},
                    "result": {"end_reason": "max_turns"}, "error": failure,
                },
            }
            for kind in ("pr", "docs"):
                with self.subTest(provider_failure=kind, expected=expected):
                    with redirect_stderr(io.StringIO()), self.assertRaises(panel_runtime.PanelError) as error:
                        panel_runtime.run_session(fake, kind, clone=self.clone)
                    self.assertIn(expected, str(error.exception))
                    self.assertEqual("max_turns" in str(error.exception), failure is None)
                    for private in ("PRIVATE_URL", "PRIVATE_CAUSE", "RAW PROVIDER RESPONSE"):
                        self.assertNotIn(private, str(error.exception))

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
        self.assertIn("## Final verdict: Changes requested", report)
        self.assertIn("**Do not merge until the major and blocker findings are resolved.**", report)
        self.assertLess(report.index("</details>", report.index("Seven review checks")),
                        report.index("## Final verdict:"))
        for reason in reasons:
            self.assertIn(reason, report.split("## Final verdict:")[1])
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
            self.assertIn(f"## Final verdict: {title}", report)
            self.assertIn("Do not merge", report.split("## Final verdict:")[1])
        fields["findings"] = [candidate]
        verdict, reasons = reporting.validate_pr(fields, self.clone, assessments, self.pr)
        report = reporting.render_pr(fields, self.clone, assessments, verdict, reasons, allow_approve=False)
        self.assertTrue(report.startswith("## PR verdict: Do not merge"))
        self.assertIn("## Final verdict: Do not merge", report)
        for allow_approve in (False, True):
            verdict, reasons = reporting.validate_pr(self.fields, self.clone, self.assessments, self.pr)
            report = reporting.render_pr(self.fields, self.clone, self.assessments, verdict, reasons,
                                         allow_approve=allow_approve)
            self.assertTrue(report.startswith("## PR verdict: Ready to merge"))
            self.assertIn("## Final verdict: Ready to merge", report)
            self.assertIn("**This PR is ready to merge based on the source review.**", report)
            self.assertIn(self.fields["reason"], report.split("## Final verdict:")[1])
            self.assertEqual("Approval requires `--allow-approve`" in report, not allow_approve)
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
                        redirect_stderr(io.StringIO()) as err, patch.object(progress, "datetime") as clock:
                    clock.now.return_value = datetime(2026, 9, 7, 12, 34, 56)
                    transcript = self.clone / f"channel-{kind}-{verbose}.txt"
                    channel = panel_runtime.PanelChannel(kind, transcript, verbose, "fixture-model")
                    channel.send_system("RAW SYSTEM DISCUSSION")
                    channel.send("Chair", "RAW CHAIR DISCUSSION")
                    for actor in actors:
                        channel.send(actor, "RAW PRIVATE DISCUSSION")
                self.assertEqual(out.getvalue(), "")
                if verbose:
                    for index, actor in enumerate(actors):
                        phase = ("plan", "draft", "verify")[index // 3] if kind == "docs" else (
                            "verify" if actor == "Verifier" else "review")
                        self.assertIn(f"[2026-09-07 12:34:56] [fixture-model] [{actor}] [{phase}] "
                                      "RAW PRIVATE DISCUSSION", err.getvalue())
                else:
                    self.assertEqual(err.getvalue(), "")
                for raw in ("RAW PRIVATE DISCUSSION", "RAW CHAIR DISCUSSION", "RAW SYSTEM DISCUSSION"):
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
                        self.assertRegex(err.getvalue(), r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
                                         r"\[-\] \[Host\] \[prepare\] Checking source\.\.\.")
                        update("Waiting for repository fetch", model="fixture-model", agent="Lead", phase="review")
                        self.assertTrue(err.flushed.wait(2), "No flushed heartbeat while work is blocked")
                        for text in ("Waiting for repository fetch...", "Still working: Waiting for repository fetch"):
                            self.assertIn(f"[fixture-model] [Lead] [review] {text}", err.getvalue())
                        self.assertIn("s elapsed;", err.getvalue())
                        self.assertIn("s total)", err.getvalue())
                        if error is not None:
                            raise error
                except BaseException as exc:
                    caught = exc
                self.assertIs(caught, error)
                self.assertFalse(any(t.name == "review-progress" for t in threading.enumerate()))
                self.assertEqual("Done: Checking source" in err.getvalue(), error is None)
                self.assertEqual(out.getvalue(), "")

    def test_cli_interrupt_stops_native_request_and_retry_wait(self):
        for phase in ("request", "retry"):
            received, release = threading.Event(), threading.Event()

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    self.rfile.read(int(self.headers["Content-Length"]))
                    if phase == "retry":
                        self.send_response(503)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                    received.set()
                    release.wait(5)
                    self.close_connection = True

                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            script = """
import sys
import review
import session_builder

def blocked():
    provider = session_builder.build_provider("offline-fixture", sys.argv[1], 180)
    provider.chat_with_retries("fixture", [{"role": "user", "content": "Fixture request."}])
    print("Unexpected completion", flush=True)

review.main = blocked
review.cli()
"""
            process = subprocess.Popen(
                [sys.executable, "-c", script, f"http://127.0.0.1:{server.server_port}/v1"],
                cwd=review.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                with self.subTest(phase=phase):
                    self.assertTrue(received.wait(5), "Native request never reached the fixture server")
                    if phase == "retry":
                        time.sleep(0.1)
                    process.send_signal(signal.SIGINT)
                    out, err = process.communicate(timeout=3)
                    self.assertEqual(process.returncode, -signal.SIGINT)
                    self.assertEqual(out, "")
                    self.assertNotIn("Unexpected completion", err)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()
                release.set()
                server.shutdown()
                server.server_close()
                worker.join()

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
                               max_turns=None, verbose=False, panel_timeout=123)
        workspace = self.clone / "guide"
        skill = fixture_skill()
        documents = fixture_documents(skill)
        module_name = "ARCHITECTURE/modules/command.md"
        rules_name = review.architecture.RULES_PATH
        cases = [(None, None)]
        for name in documents:
            cases.extend((name, state) for state in ("missing", None, "invalid", "1.0.0", "oversized"))
        for name, stamp in cases:
            for path, content in documents.items():
                target = self.clone / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            if name is not None:
                target = self.clone / name
                target.unlink()
                if stamp != "missing":
                    content = documents[name]
                    if stamp is None:
                        content = content.split("---\n", 2)[-1]
                    elif stamp == "oversized":
                        content += "x" * 12_001
                    else:
                        content = content.replace(skill.version, stamp, 1)
                    target.write_text(content)
            audited = name is not None
            report = review.architecture.Report(skill.revision, (), documents, "Source inspected.")
            with self.subTest(path=name, state=stamp), ExitStack() as stack:
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
                    self.assertIn("Checking baseline architecture", err.getvalue())
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
                    run.assert_called_once_with(builder.return_value, "docs", timeout_s=123)
                else:
                    self.assertEqual(actual_report.documents, documents)
                    self.assertNotIn("documentation workspace", err.getvalue())
                self.assertEqual("Auditing baseline architecture against source" in err.getvalue(), audited)
                self.assertEqual("skipping documentation preparation" in err.getvalue(), not audited)
                self.assertEqual("Validating documentation proposals" in err.getvalue(), audited)
                self.assertEqual(out.getvalue(), "")
                context = review.documentation_context(actual_workspace, actual_report)
                self.assertEqual("source-audited" in context, audited)
                self.assertEqual("preparation and source audit were skipped" in context, not audited)
                self.assertIn("Task Index", context)
                self.assertIn("Read when", context)
                self.assertIn("NOT executed", context)
                self.assertIn("original file and line", context)
                self.assertEqual(context.count(documents["ARCHITECTURE.md"]), 1)
                self.assertEqual(context.count(documents[rules_name]), 1)
                self.assertNotIn(documents[module_name], context)
                self.assertNotIn("also read the source checkout's original architecture files when present", context)
                expanded = review.architecture.Report(
                    actual_report.revision, (), documents | {
                        f"ARCHITECTURE/modules/unrelated-{index}.md": "UNRELATED_BODY_SENTINEL" for index in range(100)
                    }, actual_report.summary, audited=audited)
                self.assertEqual(review.documentation_context(actual_workspace, expanded), context)

    def test_default_cli_completes_without_verbose_or_transcript(self):
        skill = fixture_skill()
        documents = fixture_documents(skill)
        for name, content in documents.items():
            path = self.clone / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        snapshot = git_io.Source(self.clone, "b" * 40, "c" * 40, "")
        pr = self.pr | {"number": 1, "headRefOid": "a" * 40, "baseRefName": "main"}
        formats = {
            "canonical": lambda reply: reply,
            "multiline": lambda reply: "RESULT\n" + json.dumps(json.loads(reply[7:]), indent=2),
            "indented": lambda reply: "  " + reply,
            "fenced record": lambda reply: "Review complete.\n```json\n" + reply + "\n```",
            "fenced payload": lambda reply: "RESULT\n```json\n" + reply[7:] + "\n```",
            "bare JSON": lambda reply: json.dumps(json.loads(reply[7:]), indent=2),
            "fenced JSON": lambda reply: "```json\n" + json.dumps(json.loads(reply[7:]), indent=2) + "\n```",
        }
        cases = [(kind, fields, name, format_reply)
                 for kind, fields in (("pr", self.fields), ("issue", issue_fields("bug")))
                 for name, format_reply in formats.items()]
        for kind, fields, name, format_reply in cases:
            for verbose in (False, True):
                replies = [format_reply(reply) for reply in scripted_replies(kind, fields)]
                if name == "canonical":
                    replies.insert(0, "Unformatted response sentinel")
                provider = ScriptedProvider(replies)
                with self.subTest(kind=kind, verbose=verbose, format=name), ExitStack() as stack:
                    out = stack.enter_context(redirect_stdout(io.StringIO()))
                    err = stack.enter_context(redirect_stderr(io.StringIO()))
                    stack.enter_context(patch("sys.argv", [
                        "review.py", "--id", "1", "--repo", "a/b", "--branch", "main",
                        "--api-key", "fake", "--llm-model", "fixture", "--dry-run",
                        "--workdir", str(self.clone),
                        *(["--verbose"] if verbose else []),
                    ]))
                    stack.enter_context(patch.object(github_io, "ensure_gh_ready"))
                    stack.enter_context(patch.object(github_io, "detect_kind", return_value=kind))
                    stack.enter_context(patch.object(github_io, "fetch_pr", return_value=pr))
                    stack.enter_context(patch.object(github_io, "fetch_issue", return_value={"number": 1}))
                    pr_post = stack.enter_context(patch.object(github_io, "post_pr_review"))
                    issue_post = stack.enter_context(patch.object(github_io, "post_issue_comment"))
                    stack.enter_context(patch.object(git_io, "ensure_clone", return_value=self.clone))
                    stack.enter_context(patch.object(git_io, "prepare_source", return_value=snapshot))
                    stack.enter_context(patch.object(review.architecture, "sync_skill", return_value=skill))
                    stack.enter_context(patch.object(session_builder, "build_provider", return_value=provider))
                    stack.enter_context(patch.object(review.repo_facts, "collect", return_value="Source facts."))
                    self.assertEqual(review.main(), 0)
                    pr_post.assert_not_called()
                    issue_post.assert_not_called()
                report = out.getvalue()
                self.assertIn("## Final verdict: Ready to merge" if kind == "pr" else "## Issue assessment: bug", report)
                self.assertIn("waiting for model response", err.getvalue())
                actor = "Lead" if kind == "pr" else "Investigator"
                self.assertIn(f"[fixture] [{actor}] [review] waiting for model response", err.getvalue())
                self.assertIn("[fixture] [Verifier] [verify] waiting for model response", err.getvalue())
                self.assertEqual("requesting one result-format correction" in err.getvalue(), name == "canonical")
                self.assertIn("Dry run: nothing posted", err.getvalue())
                self.assertEqual("Unformatted response sentinel" in err.getvalue(), verbose and name == "canonical")
                self.assertEqual(fields["reason" if kind == "pr" else "response_body"] in err.getvalue(), verbose)
                self.assertNotIn("RESULT ", report)
                self.assertEqual(len(provider.calls), len(replies))
                self.assertEqual({p.relative_to(self.clone).as_posix() for p in self.clone.rglob("*")},
                                 {"app.py", "ARCHITECTURE.md", "ARCHITECTURE", "ARCHITECTURE/AGENT_RULES.md",
                                  "ARCHITECTURE/modules", "ARCHITECTURE/modules/command.md"})
                if verbose:
                    self.assertEqual(report, default_report)
                else:
                    default_report = report

    def test_kind_and_selected_source_precede_one_documentation_gate(self):
        skill = fixture_skill()
        source, guide = self.clone / "source", self.clone / "guide"
        source.mkdir()
        (source / "app.py").write_bytes((self.clone / "app.py").read_bytes())
        documents = fixture_documents(skill)
        for name, content in documents.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        actual_prepare_docs = review.prepare_docs
        for kind in ("issue", "pr"):
            for current_root in (False, True):
                events = []
                args = SimpleNamespace(repo="a/b", prompts=None, kind="auto", number=1, api_key="fake",
                                       api_base="https://example.invalid", timeout=1, workdir=self.clone,
                                       branch="release/selected", llm_model="fixture", transcript=None,
                                       max_turns=None, verbose=False, allow_approve=False, panel_timeout=123)
                (source / "ARCHITECTURE.md").write_text(
                    documents["ARCHITECTURE.md"].replace("Return a value", "Original guide. Return a value") if current_root else "Old guide.\n")
                snapshot = git_io.Source(source, "b" * 40, "c" * 40, "merged diff" if kind == "pr" else "")
                pr = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "main",
                      "state": "OPEN", "isDraft": False}
                docs = review.architecture.Report("abc123", (), documents | {"ARCHITECTURE.md": "Generated guide."}, "Checked.")

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
                               verbose=False, allow_approve=True, panel_timeout=123)
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

    def test_local_worktree_isolation_and_dirty_guard(self):
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
        self.assertEqual(git_io.git("rev-parse", "HEAD", cwd=snapshot).stdout.strip(), head)
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
                self.assertFalse(args.verbose)
                self.assertIsNone(args.transcript)
                self.assertEqual(args.panel_timeout, 900)
        with patch("sys.argv", ["review.py", "--id", "42", *options, "--panel-timeout", "120"]):
            self.assertEqual(review.parse_args().panel_timeout, 120)
        for value in ("0", "-1", "invalid"):
            with self.subTest(panel_timeout=value), \
                    patch("sys.argv", ["review.py", "--id", "42", *options, "--panel-timeout", value]), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                review.parse_args()
            self.assertEqual(error.exception.code, 2)
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
