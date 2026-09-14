---
eatmycode_version: "2.0.0"
---
# Provider requests, progress and elapsed budgets

Owner: [Review panels](../modules/harness.md)

Read when: changing `provider_io.py`, provider construction, request/retry
accounting, panel budgets, stderr measurements, progress or interruption behavior.

## Contract

`session_builder.build_provider` supplies two retries after the initial attempt,
with fixed 3-second pauses through kerness `interval_sec`. A sequence allows
three attempts and six seconds of pauses plus HTTP time. Retries resend pending
requests without restarting completed turns. `--api-timeout` applies per attempt;
native compatibility fallback may begin another sequence. Waiting cannot resolve
a persistently incompatible request (`RETRIES`, `RETRY_INTERVAL_SECONDS`).

`provider_io.ObservedProvider` keeps native `chat_with_retries` policy and wraps
the public `kerness.provider.http_post_json` seam after payload assembly. Every
POST reports logical request, attempt, retry/fallback sequence and elapsed HTTP
time. Recursive fallback resets attempt count without a new logical ID. Native
compaction lacks a start event, so the observer supplies a request/`compact`
phase attributed to docs Chair or the first registered reviewer. Empty-response
or decode retries are visible at their next attempt, but do not receive the
transport-error pause notice.

Metrics contain message counts, compact UTF-8 JSON bytes, fixed role-byte
buckets, tool-schema count/bytes and total payload bytes. Role sizes sum message
objects without array delimiters. Prompt/schema characters divided by four are
a heuristic token estimate, not a tokenizer, context guarantee or evidence of
timeout cause. Native numeric wire formatting may differ. Headers are excluded.
Only nonnegative integer `prompt_tokens`/`input_tokens` provider usage is emitted
separately. Never include payload/schema contents or names, tool arguments, raw
errors, URLs, headers or credentials (`_prompt_size`, `_Request.post`).

Panel/request ContextVars plus an RLock scope a process-global transport hook.
Observed calls serialize; unrelated threads pass through without logging.
`finally` restores hook/context. Defer stderr-write errors until the native
operation returns so broken telemetry cannot replay a successful POST. Calls
outside panel observation retain native behavior.

`panel_runtime.run_session` shares `max_elapsed_ms` across all agents, tools,
retries, fallbacks and compaction. Kerness checks action boundaries; active
calls and remaining native pauses may overrun. Host monotonic validation catches
late closing responses too and rejects publication with an elapsed-budget
diagnostic. There is no separate whole-CLI deadline or provider-request count
guarantee. Tool replies cannot reset the clock.

Execution failures retain the last observed request's model/actor/phase,
attempt/fallback label, safe HTTP outcome and configured `--api-timeout`; new
logical requests clear prior attempt detail (`ProviderProgress.failure_context`).
`run_session` normalizes elapsed expiry across failed steps, session exceptions
and late results, including native errors wrapped as provider failures. It shows
actual elapsed/configured budget and distinguishes `--panel-timeout` from the
per-attempt limit. An unsent retry retains the preceding attempt's failure;
providers without POST observation report that no HTTP attempt was observed.
`_rejection_hint` maps HTTP 400/413/422 bodies of at most 16,384 characters to
fixed guidance, reusing kerness's context classifier. Heuristic matches never
change recovery; unknown/oversized bodies direct users to gateway logs. No body
text or arbitrary field values are emitted.

Engine events identify logical waits, evidence inspection and committed turns;
POST observation distinguishes actual sends/retries/fallbacks. Docs phase labels
follow the required specialist rotation; final-summary purpose uses `summary`.
PR/issue stages use `review`/`verify`. Measurements/status never enter messages,
reports or transcripts. The [workflow owner](../modules/review-cli.md) owns the
shared timestamp/heartbeat implementation and CLI-only SIGINT handling; read it
when lifecycle or interruption changes. Heartbeat elapsed time indicates waiting,
not token streaming or provider health. OS termination bypasses Python cleanup.

## Change and Verify

Read [Panels](../modules/harness.md) for participation gates and
[Workflow](../modules/review-cli.md) for configuration/progress changes. Preserve
native retries, per-attempt timeout, sanitized errors and hook cleanup. A model
request may succeed despite failed telemetry; do not convert it into another
attempt. Avoid inferring latency causes from prompt sizes alone.

Run the [root checks](../../ARCHITECTURE.md#verification). Provider cases in
`tests/test_workflow.py` use real providers/engine with mocked transport: they
assert the 3-second policy then remove waits in fixtures, recover on retry two,
preserve completed turns, stop after three failures and retain each timeout.
They cover empty replies and compatibility fallbacks, Unicode/schema/file-read
payload measurements, usage handling, compaction, unrelated threads, hook
restoration, bounded refusal guidance/redaction and output failure without replay. Elapsed-budget cases reject late
responses/pending tools and retain timed-out tool-followup details when expiry
prevents a retry for all panels. Local HTTP subprocess cases verify SIGINT
during native calls and retry sleep. Expect `OK` and exit 0; no external provider
or GitHub write is exercised.

## Evidence and Gaps

`progress.activity` schedules at 15 seconds, but native 3-second retry sleeps
can delay Python heartbeat delivery. Synchronous observation measures completed
HTTP attempts, not token progress. Host cooperative budgets cannot forcibly
cancel in-flight native work. These limits are documented behavior, not evidence
that a specific slow review exhausted context or reached a provider timeout.
