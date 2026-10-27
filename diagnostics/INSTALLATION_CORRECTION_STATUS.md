# Installation correction status

Updated 2026-09-23. **Security corrections are implemented locally. The requested
web installer is not complete and is blocked from distribution.** Nothing from
this correction has been deployed to the live hub or to a target computer.

## Corrected

- Replaced the disconnected Flask blueprint with a FastAPI router registered in
  the existing hub and using its real session validator. Removed the hardcoded
  browser credential and arbitrary-cookie acceptance.
- Added same-origin protections for administrative mutations, bounded request
  bodies, strict reporting schemas, and a bounded request limiter.
- Added real installation dashboard markup, availability/error messages and
  event details. Rendered data is escaped/text-only. Invitation creation is
  disabled while the server reports no releasable installer.
- Serialized invitation redemption so concurrent requests cannot consume one
  single-use invitation repeatedly. Added use/expiry validation, expiring attempt
  tokens and revocation checks, including under the event write transaction.
- Enforced legal stage transitions, contiguous event sequences, scoped
  idempotency/conflict handling and terminal states. Downloader tokens cannot
  assert ONLINE or set a device identity.
- Closed SQLite connections deterministically; bounded history responses and
  surfaced stale nonterminal attempts as STATUS_UNKNOWN. Migrated old demo
  attempts to LEGACY_UNVERIFIED with unusable credentials.
- Removed the fixture download route, fake file-copy installation, broad uninstall
  deletion and automatic consent fallback. These paths now fail without touching
  the computer or claiming a successful installation.
- Added a bounded reporting queue to the **non-distributable protocol harness**.
  Optional persistence retains event IDs across process restart, without saving
  report credentials. This is not a production native downloader.
- The builder now reports NATIVE_BUILD_NOT_IMPLEMENTED rather than presenting a
  Python archive as an EXE. A separate PE format/size validator rejects archives.
- Replaced misleading fixture-installation tests with accurately named HTTP
  telemetry and distribution-gate tests. Retained real release acceptance checks
  as failing checks instead of marking the release complete.

## Verification

The corrected backend/package/harness/HTTP/security suites ran **20 tests, all
passing**, including 16 concurrent redemptions of one invitation, revoked token
rejection, forged admin cookies, CSRF, sequence/idempotency conflicts, persistence,
stale connectivity and oversized reports.

The existing installer/identity regressions plus release acceptance suite ran 25
tests: **23 passed and 2 release checks failed** because a native `.exe` and its
measured release size do not exist. The two failures are expected blockers, not
waivers or skipped tests. The actual hub auth function and router registration
are also exercised in isolation without starting agent or excluded desktop code.

Installer UI, curtain-control and installation UI regression scripts passed.
JavaScript syntax and `git diff --check` passed. No Windows installation, payload
execution, live credential use, or live deployment was performed.

Commands:

```
python -m unittest diagnostics.test_installation_backend diagnostics.test_installation_package diagnostics.test_bootstrapper diagnostics.test_installation_e2e diagnostics.test_installation_security
python -m unittest diagnostics.installer_regression diagnostics.device_curtain_regression diagnostics.installation_acceptance_review
node diagnostics/installer_ui_regression.js
node diagnostics/mirror_controls_regression.js
node diagnostics/installation_ui_acceptance_review.js
```

Run installer tests in isolated workspace/temp directories. The application
database is not a test fixture. Do not run the superseded prototype tests against
a user's real LocalAppData or registry.

## Still required before a working distribution can be released

1. A genuine consent-based Windows downloader and reproducible build under the
   agreed 1,000,000-byte limit, tested on clean Windows without Python. The old
   `.pyz` remains a rejected historical artifact, not a release candidate.
2. A verified per-user package for the actual authorized agent functionality,
   with an explicit dependency list, privilege limits, ownership records,
   transactional upgrade/recovery, and normal visible uninstall support.
3. An authenticated release manifest and verification of the actual payload
   before execution. Executable signing is separate from payload integrity.
4. A real enrollment handshake tying an approved installation to an authenticated
   agent connection. A machine GUID or downloader claim is not authentication.
5. Native downloader integration with consent/status/cancellation, coalesced
   progress, bounded retries and reporting recovery. The Python reporting harness
   does not establish this native implementation.
6. Clean standard-user Windows VM tests, failed-download/disk-full/interruption
   and rollback tests, real connection verification, then a consented staging
   pilot. Do not change the server readiness gate until these are evidenced.

The earlier review remains a historical record of defects found. This document
describes what was subsequently changed and avoids claiming the missing installer
has been delivered.
