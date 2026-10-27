# Small web installer and installation-status dashboard: handoff

Status: implementation plan, not a completed installer or production certification.
Reviewed: 2026-09-23, repository revision `83ee02b`.

## 1. Product requirements and boundaries

Provide a small Windows EXE, targeting at most **1,000,000 bytes**, for an existing website. It downloads the larger remote-support package after the person explicitly agrees to installation. Detailed progress and errors appear in the administrator dashboard; a minimizable status display and cancellation remain available on the computer. The downloader runs directly; it does not need its own separate installation.

The small file does not reduce total payload download size. Measure its release build instead of promising a size before compilation. Do not bundle Python or another large runtime in the downloader.

No unexpected reboot, application closure, privilege escalation, or automatic remote-control session. Do not hide what is being installed, bypass UAC/security controls, add antivirus exclusions, or use compatibility flags to imply administrative capabilities. Unsigned pilot builds may be blocked or warned about. Signing remains a production distribution requirement; it is not a guarantee against warnings.

Backstage/HVNC source, behavior, and testing remain outside this project. Do not inspect or change compositor, spawner, CDP, or hidden-desktop stream implementations. Existing packaging of those components is not evidence they are compatible with this proposed installation mode. Any full-product compatibility review outside this scope requires a separate task.

## 2. Verified findings in the current repository

These are targeted source-review findings, not an exhaustive security audit or a live installation test.

| Location | Observed behavior | Required action |
|---|---|---|
| `master_hub/generator.py`, `AgentGenerator._build_package` | Copies the runtime and source into a custom package, with baked configuration per build | Keep existing flow available; introduce reusable versioned releases and separate enrollment for the web installer |
| `master_hub/generator.py`, generated batch installers | Use Program Files and attempt privileged scheduled tasks | Do not reuse these scripts for the no-elevation installation path |
| `master_hub/setup_compiler.py`, `_compile_nsis` | Declares `RequestExecutionLevel user`; probes Program Files and falls back to LocalAppData | Replace permission-dependent behavior with an explicit per-user or managed machine-level product mode |
| Same NSIS template | Includes HKLM writes, all-users startup operations and privileged scheduled-task attempts despite user-level execution | Remove such operations from the per-user package; do not suppress failure and report success |
| Same NSIS template | Applies RunAsInvoker compatibility settings | Do not treat compatibility settings as privilege management; use a correctly authored package and executable manifest |
| Same NSIS template, completion block | Launches the agent, waits 1.5 seconds, prints success and displays a completion MessageBox | Respect quiet installation; verify installation separately from authenticated agent connectivity; eliminate unconditional success reporting |
| `master_hub/app.py`, download routes | Bootstrap/package handlers shown do not call `_is_authenticated`; serve paths constructed from filenames | Introduce an explicit artifact access policy and resolved-path containment checks; do not assume public package access authorizes enrollment |
| `master_hub/app.py` and `master_hub/static/app.js` | Existing generation/download UI is present; targeted search found no enrollment installation-progress workflow | Add persistent installation records, reporting API and dashboard UI |
| `device_identity.py` | Stable device identity derived from Windows MachineGuid, with fallback | Preserve identity across reinstall; do not use this identifier as an authentication secret |
| Generator disk handling | Serialized builds, space guard, temporary build cleanup and atomic ZIP publication exist | Preserve these controls; avoid one large payload copy per installation link |

The NSIS path is the current Linux server packaging path. Do not assume changes to a different compiler fallback fix what the live server actually distributes.

## 3. Decide the supported permission model first

Implement **per-user support installation** for the no-UAC pilot:

- Use a current-user application directory and current-user configuration/log locations.
- All child processes inherit ordinary user privileges.
- Do not install a system service, driver, system-wide startup entry or modify protected locations.
- Check whether the agent can actually run in this context before integrating the downloader. Record unsupported features explicitly. An ordinary user's agent cannot be assumed to control elevated applications, secure desktops, or other users' sessions.
- If a requirement needs elevation, report `ADMIN_REQUIRED`; do not repeatedly prompt, silently skip a required component, or try alternate privilege paths.
- Optional startup at the user's sign-in must be disclosed, user-controllable and removed on uninstall. Do not create multiple redundant startup mechanisms.

If full machine-level capabilities are required, choose an already-authorized managed deployment or an explicitly approved elevated installation. Do not claim the same feature set is available with neither.

References: https://learn.microsoft.com/en-us/windows/win32/msi/installation-context and https://learn.microsoft.com/en-us/windows/win32/sbscs/application-manifests.

## 4. Proposed component layout

These files/modules are proposals; they do not exist merely because they appear here.

| Component | Proposed location | Responsibility |
|---|---|---|
| Native downloader | `installer/bootstrapper/` | Minimal Windows-native EXE, consent/status UI, verified downloads, installation orchestration and reporting |
| Per-user package | `installer/package/` | Explicit installation contract, safe upgrade, uninstall and recovery |
| Installation API | `master_hub/installations.py` | Enrollment, authenticated report ingestion and administrator queries |
| Persistent records | `master_hub/installation_store.py` | Schema/migrations, transitions and event deduplication |
| Release manifest/build process | `installer/releases/` | Versioned immutable packages, integrity metadata and reproducible release records |
| Dashboard integration | `master_hub/static/app.js` and its existing page | Installation list, stage timeline, progress and errors |
| Tests | `diagnostics/installation_*` | Isolated backend tests, UI checks and documented Windows VM matrix |

Prefer a minimal native implementation using Windows-provided networking and UI facilities. Prototype and measure before selecting the final toolchain. A generic EXE can ask for a short enrollment code shown on the website; do not assume a downloaded EXE automatically inherits the browser's session. Automatic browser-to-app handoff would be a separate reviewed design.

## 5. Enrollment and reporting contract

Separate three identifiers: invitation/enrollment ID, installation-attempt ID, and stable device ID. Separate their credentials too. A public website visitor must not receive administrator credentials or permission to enroll arbitrary devices into arbitrary accounts.

Suggested API responsibilities:

1. Administrator creates/revokes a short-lived, bounded-use invitation through the authenticated dashboard.
2. After local installation consent, the downloader redeems it over HTTPS. Redemption atomically creates an attempt and returns credentials scoped to that attempt and approved release.
3. The downloader sends idempotent stage/progress events. Its credential permits reporting only its own attempt, not viewing devices, initiating remote control, or issuing commands.
4. Administrator list/detail/event APIs require the existing admin authentication and authorization. State-changing browser requests need CSRF protection appropriate to the session implementation.
5. Agent registration separately proves enrollment. Only an authenticated agent connection marks the device online; a downloader cannot assert this terminal condition by itself.

Store invitation secrets as hashes, expire/revoke credentials, rate-limit redemption/reporting, bound message sizes and redact secrets from access/application logs. Never place credentials in executable names or diagnostic output. Public immutable installer bytes may be downloadable without authentication; account binding must still require authorized enrollment.

Recommended persistent fields: attempt ID, enrollment ID, device ID when known, release/version, architecture, stage, stage start/end timestamps, event sequence, downloaded/total bytes, heartbeat receipt time, installer exit code, stable error code, sanitized explanation, correlation ID and consent-version/time. Track retries separately from stage transitions. Apply retention limits to logs.

Use the project's established database if available; otherwise add a migration-managed store such as SQLite for a single hub instance, with transactions and a documented backup procedure. Do not use an in-memory dictionary as the source of truth. Multi-instance deployment needs shared storage and atomic redemption.

## 6. State machine and user-visible behavior

Normal path:

`AWAITING_START -> STARTED -> CONSENTED -> CHECKING -> DOWNLOADING -> VERIFYING -> INSTALLING -> INSTALLED -> CONNECTING -> ONLINE`

Define `FAILED`, `CANCELLED`, `ADMIN_REQUIRED`, and `REBOOT_REQUIRED` outcomes. Connectivity is an independent status: a missing heartbeat produces `STATUS_UNKNOWN`, not an invented failure or success.

- `AWAITING_START`: invitation exists; no execution has been confirmed. A website download is not proof the application ran.
- `STARTED`: the executable has contacted the hub. If it cannot contact the hub, the administrator cannot receive this notification yet.
- `DOWNLOADING`: real bytes and total size, not estimated installation completion.
- `INSTALLING`: named stages; show a percentage only if the underlying installer supplies meaningful progress.
- `INSTALLED`: package completed and local installation checks passed.
- `ONLINE`: the hub has accepted the corresponding authenticated agent registration.

Events use increasing sequence numbers and idempotency keys. Duplicate delivery and late arrivals must not regress state. Derive timestamps used for timeouts from server receipt times; preserve client timestamps only as diagnostic data. Initial reporting cadence can be every 2 seconds with coalescing, plus immediate stage/error events. Queue a bounded local backlog when disconnected and resend safely.

Dashboard: show hostname when available, stage, version, download progress, last contact, retry count and a timeline. Distinguish download failure, integrity failure, insufficient disk, permission denial, install failure and installed-but-offline. Sanitize log text before rendering. Administrative cancellation means a signed/authenticated cancellation request checked at safe checkpoints; it is not an arbitrary command channel.

## 7. Download, installation and recovery

1. Check supported Windows/architecture, current-user writable space, existing version and concurrent installation lock.
2. Fetch an immutable release manifest over HTTPS. Include package ID, version, architecture, byte size, hash, format and compatibility requirements. Do not accept arbitrary command strings from it.
3. Download into a unique user-owned staging directory with timeout, bounded retries and cancellation. Validate TLS and allowed download origins, including redirects. Resume only when server range support and artifact identity are verified.
4. Verify size and integrity before execution. A hash fetched from the same compromised server is not independent authenticity protection. Use a signed manifest with a pinned verification key; verify Authenticode publisher signatures when signed packages are available. An unsigned pilot must disclose its limitations rather than claim signature verification occurred.
5. Run only the approved package under the chosen user context. Check the actual exit code. The package must support quiet mode without dialogs and without claiming success after ignored failures.
6. Stage updates separately from the active install. Do not delete the working version first or kill unrelated processes by a broad name/path match. Stop only the registered product instance when necessary and report that brief interruption.
7. Commit installation after local validation; restore the previous known-good version on a failed commit when safe. Define migration reversibility explicitly. A network outage after successful installation is not by itself a reason to roll back.
8. Keep diagnostics, clean only owned staging paths, and provide a visible uninstall entry that removes the product's own files/configuration/startup registration. Never remove shared user data or other applications.

There is no blanket rollback guarantee: test interruption at every mutation boundary, document non-reversible operations, and avoid them in the per-user pilot. Never force a reboot. Surface reboot-required as a separate result.

## 8. Implementation order and exit criteria

**Phase A — permission and packaging proof.** Build a per-user test package with a harmless fixture application first. Confirm standard-user install, update, cancel and uninstall on clean Windows VMs. Then assess the permitted agent functionality in a consented test environment. Do not wrap the existing contradictory installer and declare this phase done.

**Phase B — persistent backend.** Implement migrations, invitation redemption, attempt-scoped credentials, event validation and admin-only queries. Test replay, revoked/expired invitations, concurrent redemption, wrong-account access, restart persistence and out-of-order events.

**Phase C — native downloader.** Implement consent, enrollment-code flow, manifest/download verification, progress and bounded offline reporting. Confirm the release EXE is at most 1,000,000 bytes with a clean-machine test requiring no separate runtime installation. If it exceeds the limit, report the measured result and tradeoff; do not use obfuscation or disable protection to achieve size.

**Phase D — dashboard.** Add a separate Installations view; do not represent partial installations as online agents. Show live updates and recover state after a page reload. Keep progress available to both administrator and person installing.

**Phase E — integration and rollout.** Use localhost and a staging HTTPS deployment before production. Run a single consented pilot, verify the stage timeline against local logs and a real authenticated agent heartbeat, then enable invitation creation more broadly. Retain the existing download flow while the new flow is piloted. Publish one immutable payload per version/architecture rather than building per invitation. Keep release retention and disk monitoring.

Do not change OTA deployment behavior as a side effect. Do not deploy this plan, rebuild agents, or distribute a downloader until an implementation passes the gates below.

## 9. Required verification matrix

| Scenario | Expected result |
|---|---|
| Standard user, clean supported Windows | No elevation request for supported per-user features; no protected system changes |
| Feature needs administrative access | Explicit unsupported/admin-required outcome; no bypass or false success |
| User declines or cancels | No agent enrollment/start after cancellation; safe staged-file cleanup |
| Network lost at each stage | Accurate unknown/retry status; eventual idempotent reporting |
| Tampered/truncated payload or invalid manifest | Refuse execution and report verification failure |
| Disk fills during download/install | Clear stage-specific failure; previous installation remains usable |
| Crash/power loss during upgrade | Deterministic recovery; no success inferred from a stale log |
| Reinstall or simultaneous attempts | One stable device, serialized installation, no duplicate product instances |
| Expired/replayed invitation or wrong report credential | Denied without exposing another attempt's data |
| Hub restart and browser refresh | Persisted stage/event history restored |
| Installer exits successfully but agent cannot connect | Installed/connecting or connectivity error, never falsely online |
| Unsupported CPU architecture or blocked unsigned file | Clear compatibility/local-security limitation; no security-control disabling |
| Normal user activity during install | No forced restart, unrelated application closure, unexpected dialog or focus theft |
| Uninstall | Product removed cleanly; unrelated data and applications preserved |

For Windows integration tests record OS/build, user privilege level, package hash/version, downloader size, exit codes and actual prompts. Native pixel/control functionality must only be tested with permission on the physical desktop; exclude Backstage testing.

## 10. What was tested while preparing this handoff

Executed successfully on 2026-09-23:

```
C:\Python314\python.exe -m unittest diagnostics.installer_regression diagnostics.device_curtain_regression
node diagnostics/installer_ui_regression.js
```

Result: 14 Python tests passed; installer UI regression passed. The failure messages printed by compiler fixture tests are expected simulated failures. Fixtures do not execute a real agent or modify Windows hardware settings.

These checks cover existing packaging/configuration behavior and selected regressions. They do **not** establish that the proposed downloader exists, that the current full agent works without elevation, that rollback is complete, or that installation telemetry is implemented. No live deployment or runtime code changes were made for this handoff.

Deliverables expected from the next programmer: native downloader source and measured build, tested per-user package, API/schema migrations, dashboard UI, credential/threat review, VM test evidence, release/rollback runbook and a candid list of unsupported capabilities.
