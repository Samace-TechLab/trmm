# Web installer implementation review

Reviewed 2026-09-23 against the supplied working tree on base commit `83ee02b`.

**Decision: do not release. This is a partially implemented prototype, not completion of phases A–E.** Its broad component layout follows the handoff, but the executable, real installation, integration, authentication and reliability requirements are unmet.

No runtime fixes or live deployment were performed during this review. Added acceptance tests intentionally fail until the implementation satisfies the requirements. Backstage/HVNC implementations and OTA were excluded.

## Verified test results

| Check | Result | Meaning |
|---|---|---|
| Programmer's six Python suites | 21 passed in 3.253 seconds | Reproduced, with filesystem/DB isolation and real registry access disabled |
| Programmer's `test_installation_ui.js` | Passed | Checks three function-name substrings; does not actually validate UI integration or behavior |
| `node --check master_hub/static/app.js` | Passed | JavaScript syntax is valid |
| New `installation_acceptance_review.py` | 11 checks: **10 failed, 1 passed** | Only the Python archive byte-size check passed; functional/security acceptance failed |
| New `installation_ui_acceptance_review.js` | **2 failed** | Missing page markup and unescaped diagnostic HTML |

The supplied tests use a separately constructed Flask app and dummy payload bytes. The purported end-to-end test directly calls `store.record_event(..., stage='ONLINE')`; it does not execute an agent or observe an authenticated heartbeat. Passing these tests is not evidence of a working Windows installer, actual hub integration, rollback, or standard-user compatibility.

The test wrapper is `diagnostics/mirror_live/review_installation_run.py`. It redirects LocalAppData/temp/DB files to an isolated workspace directory and disables real registry access. Running the original tests without isolation can write fixture files into the user's real TRMM directory; its uninstall test can attempt to remove the real HKCU startup value. Do not run them unmodified on a production workstation.

## Release-blocking findings

### 1. No native Windows executable was produced

`installer/bootstrapper/build_bootstrapper.py:33` creates a Python zipapp and returns its `.pyz` path at line 46. The `.exe` variable is unused. The existing artifact is `trmm_web_installer.pyz`, 11,584 bytes, and starts with `#!`, not the Windows PE `MZ` header.

**Impact:** the claimed 11 KB standalone Windows EXE does not exist. A Python archive requires Python; the size measurement excludes that runtime. Naming the Python class `NativeBootstrapper` does not make it native.

**Required:** build a genuine executable, inspect its PE format/architecture, measure the release artifact, and prove it launches on clean supported Windows without Python. Do not simply rename the archive to `.exe`.

### 2. API is not integrated into the real hub

The actual `master_hub/app.py:18` imports FastAPI and creates a FastAPI application at line 52. It neither imports nor registers the new installation module. `master_hub/installations.py` defines a Flask Blueprint. The supplied tests register that blueprint in their own Flask application.

**Impact:** passing tests for the isolated Flask service do not demonstrate that `/api/installations/*` exists in the real hub.

**Required:** use the existing FastAPI architecture and real authentication dependencies, register the router, and run integration checks against the actual application with other functionality stubbed as needed. Adding Flask as a dependency alone will not integrate the routes.

### 3. Administrative authentication is a bypassable stub

`master_hub/installations.py:7` accepts either a hardcoded header value or any nonempty cookie called `session`. The same header value is shipped in browser JavaScript at `master_hub/static/app.js:1193` and line 1250.

**Reproduced:** an arbitrary invalid session cookie received HTTP 200 from the isolated attempts-list endpoint.

**Impact:** exposing this blueprint would expose administrative installation functions without valid administrator authentication. This review did not expose it on the live server.

**Required:** remove the stub and browser credential, use the hub's validated session and authorization model, and test forged/expired sessions, unauthenticated requests and CSRF protection. Do not deploy this route set first and plan to fix authentication later.

### 4. Dummy bytes are reported as a successful agent installation

`installer/bootstrapper/bootstrapper.py:103` downloads `/static/fixture_agent.exe`. The endpoint in `master_hub/installations.py:72` supplies a fixture. `installer/package/per_user_installer.py:55` merely copies one file and returns `INSTALLED`.

**Reproduced:** a text file containing `THIS IS NOT AN AGENT` was accepted as installed in an isolated directory. No payload was executed by review tests.

**Impact:** the implementation does not install the real agent/runtime/configuration, launch it, or establish device enrollment. It therefore cannot substantiate silent, no-elevation agent installation.

**Required:** keep fixtures confined to tests. Define and validate an actual per-user package contract and all runtime dependencies; validate local installation and separately authenticate agent registration. Explicitly document unavailable machine-level capabilities.

### 5. Payload verification is not implemented

The downloader computes a SHA-256 value, but never compares it with an expected value. Its integrity check at `bootstrapper.py:136` only rejects an empty file. There is no fetched/verified signed release manifest despite the docstring's claim.

**Reproduced:** arbitrary nonempty downloaded bytes were accepted and copied into the isolated installation directory.

**Required:** validate allowed origin/HTTPS, release, size and expected digest; authenticate the manifest and reject mismatches before any installation. Signing the executable later does not replace downloaded-package verification now.

### 6. Explicit consent is bypassed when there is no console

`bootstrapper.py:153`, `prompt_user_consent`, returns True when stdin is absent or noninteractive. There is also an `--auto-consent` path.

**Reproduced:** `sys.stdin=None` resulted in consent being granted.

**Required:** implement an actual consent/status interface for the website distribution flow. Missing UI or noninteractive execution must not be treated as visitor approval. A separately authorized enterprise deployment is a different flow, not a fallback for this one.

### 7. Progress reporting can fabricate ONLINE and regress completed states

`master_hub/installation_store.py:145` allows the attempt reporting credential to submit every listed stage, including ONLINE. It stores sequence numbers but does not use them to enforce ordering or legal transitions; line 183 unconditionally updates current state.

**Reproduced:** an attempt token asserted ONLINE without an agent connection; an older DOWNLOADING event replaced INSTALLED; INSTALLING replaced FAILED.

**Required:** server-only authenticated connectivity confirmation, enforced transitions, per-attempt monotonic ordering and transactional event ingestion. Terminal attempts must not restart without a defined new attempt/retry operation.

### 8. Telemetry is not resilient and can substantially slow downloads

`bootstrapper.py:40`, `report_stage`, catches network failures and returns False. It saves no queue and never replays the failed event.

**Reproduced:** a failed STARTED report was discarded when CONSENTED was subsequently sent.

The download loop also waits for a synchronous HTTP reporting request for each 8 KB chunk. A 30 MiB file would generate roughly 3,840 reports, each of which can wait up to 10 seconds on failure. This contradicts low-disruption downloading and coalesced telemetry.

**Required:** bounded durable reporting queue, stable retry identifiers, bounded backoff, coalesced progress and reporting independent of the download read loop. Add heartbeat/stale-state handling; loss of reports must become status unknown, not silent apparent progress.

### 9. Dashboard is incomplete and has unsafe HTML rendering

`app.js:1207` looks for `installationsTableBody`, but the actual `master_hub/static/index.html` has no such element. Missing markup causes the renderer to return immediately. There is no integrated invitation control in that page.

`app.js:1215` injects release/architecture/error fields into `innerHTML` without escaping. Those fields originate from enrollment/report requests.

**Reproduced:** inert diagnostic markup was inserted as HTML rather than rendered as text. This confirms an injection sink; no executable browser payload was used.

**Required:** implement the actual page/navigation and controls, use text-safe rendering, display API failures, and test the rendered UI rather than searching function names. Treat untrusted server data as text. Add event detail and last-contact/unknown states.

### 10. Rollback, upgrade safety and uninstall verification are absent

`per_user_installer.py` directly copies into the final directory. There is no versioned staging/commit, installation lock, preserved previous version or rollback procedure. `uninstall()` ignores removal errors and still returns UNINSTALLED; its `remove_logs` argument does not govern retention. This code does not provide a visible Windows uninstall registration.

**Required:** implement and test safe update/cancellation/recovery boundaries and check actual removal results. Do not claim success after silently ignored errors. Avoid modifying the original existing installer until the replacement's contract and migration are proven.

## Additional source-review concerns

- Invitation redemption checks the use limit before a later UPDATE without an explicit serialized read/conditional claim. Concurrent single-use redemption needs an atomic transaction and a race test. This review identified the gap from source; it did not run a concurrent redemption reproduction.
- Invitations can have no expiration; browser codes use `Math.random`; no rate limiting or strict request schema is implemented. Use server-generated secure tokens, expiry and bounded attempts.
- Reporting tokens have no expiry/revocation model. Do not assume revoking an invitation revokes a previously issued attempt credential.
- Idempotency keys are global rather than scoped/validated against the attempt and original payload. Duplicate sequence numbers are not uniquely constrained.
- SQLite connection context managers commit/rollback but do not explicitly close connections. ResourceWarnings were observed during acceptance tests. Close connections deterministically.
- Shared staging path `TRMM/staging/agent.exe` has no attempt isolation or installation lock. Concurrent attempts may overwrite each other's data.
- Architecture and release are hardcoded/client-supplied; no compatibility validation is demonstrated.
- The package capability check compares requested feature names to a list. That is not evidence that the actual agent can operate under ordinary user privileges.
- No clean-machine, interruption, power-loss, low-disk, authentic heartbeat, production TLS or real standard-user installation evidence was supplied or produced during this review.

## Phase assessment

| Phase | Assessment |
|---|---|
| A: Per-user package proof | Prototype file copier and feature-name check; real package/permission proof missing |
| B: Backend/API | SQLite prototype exists; authentication, state integrity and actual hub integration are blockers |
| C: Native bootstrapper | Python script/archive only; no native EXE, verification or resilient telemetry |
| D: Dashboard | JavaScript scaffolding; missing page integration and unsafe rendering |
| E: End-to-end proof | Fixture simulation only; no real installation or authenticated agent heartbeat |

## Correction and acceptance order

1. Keep this version out of production. Correct the completion report to distinguish prototypes from verified features.
2. Fix consent, authentication, integrity verification and output escaping before enabling any new endpoints or distribution.
3. Integrate backend with the real FastAPI app, enforce atomic enrollment/event semantics, and add durable reporting.
4. Establish a real, supported per-user agent package with explicit limits and recovery/uninstall behavior.
5. Produce and measure a genuine Windows downloader; prove it starts without Python and does not request privileges for the supported user-mode flow.
6. Integrate the actual dashboard and test visible behavior, connectivity loss and error reporting.
7. Make the acceptance tests pass without weakening assertions or replacing real flows with fixtures. Retain fixture unit tests, but label them honestly.
8. Complete the clean Windows VM matrix from `INSTALLATION_HANDOFF.md`, then a consented staging pilot with authentic agent registration. Publish measured results and remaining limitations before release.

The new acceptance tests are in `diagnostics/installation_acceptance_review.py` and `diagnostics/installation_ui_acceptance_review.js`. They should remain failing until the relevant behavior is implemented; they are not a complete replacement for the handoff's integration matrix.
