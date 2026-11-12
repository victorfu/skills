# Hybrid watch setup and lifecycle

Use for the skill's default hybrid mode unless the user requests poll or forbids webhook setup. `gh webhook forward` is intended for local development/testing, not production webhook hosting. It requires the `cli/gh-webhook` extension and repository webhook access; only one forwarding session can use a repository at a time. Do not replace someone else's hook, switch accounts or broaden credentials to make it work. If unavailable, report the reason and use the helper's polling fallback. See [GitHub's forwarding documentation](https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/using-the-github-cli-to-forward-webhooks-for-testing).

## Start the receiver

Verify `gh webhook forward --help`. If the extension is missing, report that and use polling fallback without installing it. Install with `gh extension install cli/gh-webhook` only when the user explicitly authorizes installation; environment permissions still apply. Use a fresh private scratch directory per watch, outside the repository. Keep the same paths throughout the session. Do not reuse a poll state file for hybrid or run multiple consumers for one state file.

If the client cannot keep a managed background process, skip the receiver and report polling fallback; do not run the long-lived receiver in the foreground. Otherwise run it in a managed background command, keeping its process/session handle so it can be stopped. On Windows, if using `Start-Process`, use `-WindowStyle Hidden`. Commands below use `python3`; on Windows use `py -3` or a verified Python 3 `python` executable if needed.

The receiver exits 0 only for a requested stop or its lifetime limit. If `gh webhook forward` cannot start or exits (missing extension, no webhook access, another session already forwarding), the receiver exits 1, prints the reason on stderr and records it as `reason` in the signal file; the forwarder's own error output is kept in `<scratch>/signal.json.log`. Check shortly after starting that the receiver is still running; if it is not, report that reason and continue with the polling fallback.

```sh
python3 <skill-dir>/scripts/webhook_receiver.py <PR-URL> --signal <scratch>/signal.json --lifetime 14400
```

Set lifetime to the user's watch time limit (default 4 hours). The receiver binds only to loopback on a random port with an unguessable route and starts `gh webhook forward` for the verified host/repository. It records a heartbeat and generation in the signal file, not comments or instructions. PR events are filtered by PR number; repository CI events wake conservatively because fork/check payloads can omit PR associations. The helper always queries the current PR and confirms that the head stayed stable across its snapshot; webhook payloads never directly authorize fixes. Duplicate delivery IDs are suppressed within a bounded in-memory cache; replay after restart is harmless because API state and pending batches determine work.

The receiver stays running during address rounds. Its signal file is separate from the helper's state file; only the helper writes work state. No public endpoint, production service, or webhook secret is provisioned by these scripts.

## Wait, handle, acknowledge

```sh
python3 <skill-dir>/scripts/watch_pr.py <PR-URL> --mode hybrid \
  --state <scratch>/hybrid-state.json --signal <scratch>/signal.json \
  --reconcile 300 --interval 60 --settle 60 --quiet 600 --max-wait 540
```

Reuse author filters and timing overrides on every invocation. Always pass `--mode hybrid` for the skill's default watch: the standalone helper keeps its legacy `poll` default when `--mode` is omitted for compatibility with existing callers and poll state files. Hybrid always queries on startup and after an address round; healthy forwarding wakes it early, otherwise full reconciliation runs every 300 seconds. A missing, stopped or stale receiver falls back to the 60-second interval. Keep `--mode hybrid` and the same state/signal paths in this fallback, even if the signal file was never created; do not switch to `--mode poll` or reuse poll state. Each `waiting` event carries `receiver_active`; when it is false, `receiver_reason` says why. Tell the user when a watch ran on the polling fallback instead of describing it as hybrid. A receiver process can remain alive while its upstream connection is unhealthy, so periodic reconciliation always remains enabled. Settle, quiet and max-wait have independent deadlines and each causes a fresh query before a decision. This is API reconciliation, not guaranteed replay of transient events that disappeared before a query.

`baseline`, `feedback` and `ci_failed` carry `batch_id`. They are durably saved before output and re-emitted until acknowledged. Follow the main skill's event table; inspect baseline feedback and perform an address round when needed, then acknowledge even if baseline required no action. Complete and record all justified fixes/replies before acknowledging:

```sh
python3 <skill-dir>/scripts/watch_pr.py <PR-URL> --mode hybrid \
  --state <scratch>/hybrid-state.json --signal <scratch>/signal.json \
  --ack <completed-batch-id>
```

This acknowledges and resumes waiting in the same invocation; repeat timing/author overrides here too. Retrying the last successful acknowledgment is safe. Unknown IDs fail rather than discard work. `waiting`, `quiet` and `closed` need no acknowledgment. When stopping with incomplete work, leave its batch unacknowledged and report it.

On restart, read the durable batch and round records, then inspect current threads, branch, commits and CI before continuing. A replay means delivery was not acknowledged; it does not prove that earlier pushes/replies failed. Pending feedback may refer to an older head and must be reverified under the address workflow. Closed PRs stop immediately; pending CI for an obsolete head is discarded and current-head CI is reconciled. Comment text and review verdicts are versioned in full, including edits beyond emitted excerpts; a comment whose diff position moves or becomes outdated after a push is not delivered again. Settle progress survives helper restarts. Preserve state on errors; do not delete it to bypass a recovery problem.

OS locks prevent simultaneous hybrid consumers or receivers sharing their respective files and release on process exit/crash. The round and total watch limits remain the agent's responsibility, as in poll mode.

## Stop and validate

On quiet, closure, stop limits, errors or user interruption, create an empty file at `<scratch>/signal.json.stop` and wait for the receiver to exit. It terminates and waits for its owned `gh webhook forward` process. If it cannot respond, stop the owned background session/process using its saved handle; do not kill unrelated `gh` processes. The receiver also stops at its lifetime limit, and removes an old stop marker on a deliberate restart. After abrupt termination, confirm the owned forwarder is gone before restarting. Keep state/round records for recovery.

Offline tests cover scheduling, restart/acknowledgment, HTTP filtering, locks and state changes. They do not establish real GitHub forwarding permissions, availability or end-to-end agent delivery; report actual live validation separately.
