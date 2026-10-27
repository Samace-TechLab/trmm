"""Acceptance checks for the proposed web installer; never executes a payload.

These intentionally assert required behavior, not the current prototype's behavior.
All databases/files are isolated; no real agent/hub or registry writes are used.
"""
import ast
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = ROOT / 'diagnostics' / 'mirror_live' / 'installation-review'
BASE.mkdir(exist_ok=True)
tempfile.tempdir = str(BASE)
from master_hub.installation_store import InstallationStore
from installer.bootstrapper.bootstrapper import NativeBootstrapper
from installer.package.per_user_installer import PerUserInstaller


class AcceptanceReview(unittest.TestCase):
    def setUp(self):
        # Retain isolated fixtures for review; never delete real product paths.
        self.work = Path(tempfile.mkdtemp(prefix='acceptance-'))
        self.store = InstallationStore(str(self.work / 'test.db'))

    def attempt(self):
        inv = self.store.create_invitation('test-invitation')
        result, error = self.store.redeem_invitation('test-invitation')
        self.assertIsNone(error)
        return inv, result

    def test_release_is_a_windows_executable(self):
        from installer.bootstrapper.build_bootstrapper import validate_windows_executable
        artifact = ROOT / 'installer/bootstrapper/dist/trmm_web_installer.exe'
        self.assertTrue(artifact.is_file(), 'Release remains blocked: a real Windows executable is missing')
        validate_windows_executable(artifact)

    def test_native_package_size_limit(self):
        artifact = ROOT / 'installer/bootstrapper/dist/trmm_web_installer.exe'
        self.assertTrue(artifact.is_file(), 'Cannot certify size of a missing native executable')
        self.assertLessEqual(artifact.stat().st_size, 1_000_000)

    def test_real_hub_registers_installation_routes(self):
        source = (ROOT / 'master_hub/app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertTrue(any('installations' in ast.unparse(n) for n in imports),
                        'Actual FastAPI hub has no installation module integration')
        # Execute the actual auth function and router registration without hub
        # background threads, agent initialization, or excluded desktop modules.
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from master_hub.auth import AuthManager
        from master_hub.installations import create_installations_router
        auth = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_is_authenticated')
        registration = next(n for n in tree.body if isinstance(n, ast.Expr)
                            and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
                            and n.value.func.attr == 'include_router'
                            and 'create_installations_router' in ast.unparse(n))
        app = FastAPI()
        ns = {'app':app, 'Request':Request, 'AuthManager':AuthManager,
              'create_installations_router':lambda authenticate: create_installations_router(authenticate, lambda: self.store)}
        exec(compile(ast.Module(body=[auth, registration], type_ignores=[]), '<actual hub registration>', 'exec'), ns)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/installations/status').status_code, 401)
            token = AuthManager.create_session('review')
            try:
                response = client.get('/api/installations/status', headers={'Authorization':'Bearer ' + token})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()['distribution_enabled'])
            finally:
                AuthManager.destroy_session(token)

    def test_no_consent_is_not_approval(self):
        flow = NativeBootstrapper('https://example.invalid', 'unused')
        with patch('sys.stdin', None):
            self.assertFalse(flow.prompt_user_consent(), 'No interactive console silently grants consent')

    def test_admin_cookie_must_be_validated(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from master_hub.installations import create_installations_router
        from master_hub.auth import AuthManager
        app = FastAPI()
        app.include_router(create_installations_router(lambda req: AuthManager.validate_session(req.cookies.get('trmm_session')), lambda: self.store))
        with TestClient(app) as client:
            client.cookies.set('trmm_session', 'invalid-not-authenticated')
            self.assertIn(client.get('/api/installations/attempts').status_code, (401, 403))

    def test_reporter_cannot_assert_agent_online(self):
        _, attempt = self.attempt()
        ok, _ = self.store.record_event(**attempt, seq=1, idempotency_key='online', stage='ONLINE')
        self.assertFalse(ok, 'Downloader token must not establish an authenticated agent connection')

    def test_late_events_do_not_regress_stage(self):
        _, attempt = self.attempt()
        for seq, stage in enumerate(('STARTED', 'CONSENTED', 'CHECKING', 'DOWNLOADING', 'VERIFYING', 'INSTALLING', 'INSTALLED'), 1):
            self.assertTrue(self.store.record_event(**attempt, seq=seq, idempotency_key=f'event-{seq}', stage=stage)[0])
        self.store.record_event(**attempt, seq=1, idempotency_key='old', stage='DOWNLOADING')
        self.assertEqual(self.store.list_attempts()[0]['current_stage'], 'INSTALLED')

    def test_failed_terminal_state_does_not_accept_installing(self):
        _, attempt = self.attempt()
        self.store.record_event(**attempt, seq=1, idempotency_key='failed', stage='FAILED')
        self.store.record_event(**attempt, seq=2, idempotency_key='resume', stage='INSTALLING')
        self.assertEqual(self.store.list_attempts()[0]['current_stage'], 'FAILED')

    def test_nonexecutable_payload_is_not_successful_installation(self):
        payload = self.work / 'invalid.exe'; payload.write_bytes(b'THIS IS NOT AN AGENT')
        installer = PerUserInstaller()
        installer.target_dir = str(self.work / 'installed')
        installer.config_dir = str(self.work / 'installed/config')
        installer.log_dir = str(self.work / 'installed/logs')
        result = installer.install(str(payload), enable_startup=False)
        self.assertNotEqual(result['status'], 'INSTALLED')

    def test_missing_manifest_verification_rejects_download(self):
        class Response(io.BytesIO):
            headers = {'Content-Length': '17'}
        flow = NativeBootstrapper('https://example.invalid', 'test')
        def post(path, body):
            return {'attempt_id':'isolated', 'report_token':'isolated'} if path.endswith('/redeem') else {'status':'ACCEPTED'}
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.work)}), \
             patch.object(flow, '_http_post', side_effect=post), \
             patch('urllib.request.urlopen', return_value=Response(b'UNVERIFIED_BYTES!')):
            result = flow.run()
        self.assertEqual(result['status'], 'FAILED', 'Nonempty bytes were installed without an expected hash/signature')

    def test_failed_reports_are_retried(self):
        flow = NativeBootstrapper('https://example.invalid', 'unused')
        flow.attempt_id, flow.report_token = 'isolated', 'isolated'
        delivered = []
        def post(path, body):
            delivered.append(body)
            if len(delivered) == 1: raise OSError('simulated network loss')
            return {'status':'ACCEPTED'}
        with patch.object(flow, '_http_post', side_effect=post):
            flow.report_stage('STARTED')
            flow.report_stage('CONSENTED')
        self.assertTrue(any(e['stage'] == 'STARTED' for e in delivered[1:]), 'Failed event discarded instead of queued/retried')


if __name__ == '__main__':
    unittest.main(verbosity=2)
