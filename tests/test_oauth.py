"""No external connections or real credentials. Callback tests bind loopback only."""
import contextlib
import io
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
import urllib.error
import urllib.parse
import urllib.request
from bridge import oauth


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = oauth.TokenStore(Path(self.tmp.name) / 'private' / 'tokens.dat')
        self.payload = {'accessToken': 'mock-access-sensitive', 'refreshToken': 'mock-refresh-sensitive',
                        'tokenType': 'Bearer', 'expiresIn': '86400'}

    def tokens(self):
        return dict(oauth.normalize_tokens(self.payload), clientId='mock-client')

    def test_credentials_environment_and_config(self):
        p = Path(self.tmp.name) / 'client.json'
        p.write_text(json.dumps({'clientId': 'file-id', 'clientSecret': 'file-secret'}))
        with patch.dict(os.environ, {'CHZZK_CLIENT_ID': 'env-id', 'CHZZK_CLIENT_SECRET': 'env-secret'}):
            self.assertEqual(oauth.credentials(p), ('env-id', 'env-secret'))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(oauth.credentials(p), ('file-id', 'file-secret'))
            with self.assertRaises(oauth.OAuthError): oauth.credentials()

    def test_store_roundtrip_and_atomic_failure(self):
        self.store.save(self.tokens())
        self.assertEqual(self.store.load()['refreshToken'], self.payload['refreshToken'])
        before = self.store.path.read_bytes()
        with patch.object(oauth.os, 'replace', side_effect=OSError('mock-sensitive')):
            with self.assertRaises(OSError): self.store.save(dict(self.tokens(), refreshToken='rotated'))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.store.path.parent.glob('.tokens-*')), [])
        if os.name != 'nt':
            self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
            os.chmod(self.store.path, 0o644)
            with self.assertRaises(oauth.OAuthError): self.store.load()

    def test_lock_prevents_concurrent_refresh(self):
        with self.store.lock():
            with self.assertRaises(oauth.OAuthError):
                with self.store.lock(): pass
        with self.store.lock(): pass

    def test_refresh_rotates_and_never_retries(self):
        self.store.save(self.tokens())
        request = Mock(return_value=dict(self.tokens(), refreshToken='rotated'))
        result = oauth.refresh_tokens('mock-client', 'mock-secret', self.store, force=True, request=request)
        self.assertEqual(result['refreshToken'], 'rotated')
        self.assertEqual(self.store.load()['refreshToken'], 'rotated')
        self.assertEqual(request.call_args.args[0], {'grantType': 'refresh_token',
            'clientId': 'mock-client', 'clientSecret': 'mock-secret', 'refreshToken': 'mock-refresh-sensitive'})
        request.reset_mock()
        oauth.refresh_tokens('mock-client', 'mock-secret', self.store, request=request)
        request.assert_not_called()
        request.side_effect = oauth.OAuthError('fixed failure')
        with self.assertRaises(oauth.OAuthError):
            oauth.refresh_tokens('mock-client', 'mock-secret', self.store, force=True, request=request)
        request.assert_called_once()
        self.assertEqual(self.store.load()['refreshToken'], 'rotated')
        with self.assertRaises(oauth.OAuthError):
            oauth.refresh_tokens('different-client', 'mock-secret', self.store, request=request)

    def test_response_validation(self):
        self.assertGreater(oauth.normalize_tokens(self.payload)['expiresAt'], time.time())
        for change in ({'expiresIn': 'nan'}, {'expiresIn': '-1'}, {'tokenType': 'Other'},
                       {'refreshToken': ''}, {'accessToken': None}):
            with self.subTest(change=change), self.assertRaises(oauth.OAuthError):
                oauth.normalize_tokens(dict(self.payload, **change))
        with self.assertRaises(oauth.OAuthError): oauth.normalize_tokens({'content': {}, 'code': 401})

    def test_cli_never_prints_secrets_or_storage_errors(self):
        output = io.StringIO()
        with patch.object(oauth, 'TokenStore', return_value=self.store), \
             patch.dict(os.environ, {'CHZZK_CLIENT_ID': 'mock-client',
                                     'CHZZK_CLIENT_SECRET': 'mock-secret'}), \
             patch.object(oauth, 'login', side_effect=OSError('mock-secret')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(oauth.main(['login']), 1)
        self.assertNotIn('mock-secret', output.getvalue())
        self.store.save(self.tokens())
        output = io.StringIO()
        with patch.object(oauth, 'TokenStore', return_value=self.store), contextlib.redirect_stdout(output):
            self.assertEqual(oauth.main(['status']), 0)
        for value in self.payload.values():
            if value.startswith('mock-'): self.assertNotIn(value, output.getvalue())

    def test_https_request_and_sanitized_errors(self):
        response = Mock()
        response.read.return_value = json.dumps(self.payload).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(oauth.urllib.request, 'build_opener', return_value=opener):
            oauth.post_token({'clientSecret': 'mock-secret'})
            req = opener.open.call_args.args[0]
            self.assertEqual(req.full_url, oauth.TOKEN_URL)
            self.assertEqual(req.get_method(), 'POST')
            self.assertEqual(json.loads(req.data), {'clientSecret': 'mock-secret'})
            for code in (302, 401, 403, 429, 500):
                opener.open.side_effect = urllib.error.HTTPError('mock-sensitive-url', code,
                    'mock-sensitive-body', {}, io.BytesIO(b'mock-sensitive-body'))
                with self.assertRaises(oauth.OAuthError) as error: oauth.post_token({})
                self.assertNotIn('mock-sensitive', str(error.exception))
            opener.open.side_effect = urllib.error.URLError('mock-sensitive')
            with self.assertRaises(oauth.OAuthError) as error: oauth.post_token({})
            self.assertNotIn('mock-sensitive', str(error.exception))
        self.assertIsNone(oauth.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def callback(self, path, host='127.0.0.1:18766'):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request('http://127.0.0.1:18766' + path, headers={'Host': host})
        try:
            with opener.open(req, timeout=3) as r: return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def run_login(self, action, request=None, timeout=3):
        ready = threading.Event()
        errors = []
        urls = []
        request = request or Mock(return_value=oauth.normalize_tokens(self.payload))
        def worker():
            try:
                oauth.login('mock-client', 'mock-secret', self.store, timeout=timeout,
                            open_browser=lambda url: urls.append(url) or True,
                            request=request, ready=lambda _: ready.set())
            except Exception as e: errors.append(e)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(ready.wait(3))
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(urls[0]).query)
                self.assertEqual(set(query), {'clientId', 'redirectUri', 'state'})
                self.assertEqual(query['redirectUri'], [oauth.REDIRECT_URI])
                action(query['state'][0])
            finally:
                thread.join(6)
            self.assertFalse(thread.is_alive())
        self.assertEqual(out.getvalue(), '')
        return errors, request

    def test_real_callback_rejects_forgery_then_saves(self):
        def action(state):
            self.assertEqual(self.callback('/favicon.ico')[0], 404)
            self.assertEqual(self.callback('/callback?code=leak&state=wrong')[0], 400)
            self.assertEqual(self.callback('/callback?code=leak&state='+state, 'evil.example')[0], 400)
            self.assertEqual(self.callback('/callback?code=a&code=b&state='+state)[0], 400)
            self.assertEqual(self.callback('/callback?state='+state)[0], 400)
            self.assertEqual(self.callback('/callback?code=x&state='+state+'&state='+state)[0], 400)
            status, body, headers = self.callback('/callback?code=mock-code&state='+state)
            self.assertEqual(status, 200)
            self.assertNotIn(b'mock-', body)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        errors, request = self.run_login(action)
        self.assertEqual(errors, [])
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0]['code'], 'mock-code')
        self.assertEqual(self.store.load()['clientId'], 'mock-client')
        # Listener stops after one accepted callback; no replay exchange is possible.
        with self.assertRaises(urllib.error.URLError): self.callback('/callback?code=mock-code&state=replay')

    def test_callback_denied_and_api_failure(self):
        errors, request = self.run_login(lambda s: self.assertEqual(
            self.callback('/callback?error=access_denied&state='+s)[0], 400))
        self.assertIsInstance(errors[0], oauth.OAuthError)
        request.assert_not_called()
        self.assertFalse(self.store.path.exists())
        errors, request = self.run_login(lambda s: self.assertEqual(
            self.callback('/callback?code=mock-code&state='+s)[0], 502),
            request=Mock(side_effect=oauth.OAuthError('mock-sensitive')))
        self.assertNotIn('mock-sensitive', str(errors[0]))
        self.assertFalse(self.store.path.exists())

    def test_timeout_browser_failure_port_conflict(self):
        errors, request = self.run_login(lambda _: None, timeout=0.1)
        self.assertIsInstance(errors[0], oauth.OAuthError)
        request.assert_not_called()
        with self.assertRaises(oauth.OAuthError):
            oauth.login('mock-client', 'mock-secret', self.store, open_browser=lambda _: False)
        with oauth.CallbackServer(('127.0.0.1', 18766), oauth.CallbackHandler):
            with self.assertRaises(oauth.OAuthError):
                oauth.login('mock-client', 'mock-secret', self.store, open_browser=Mock())

    def test_token_api_status_and_format_diagnostics_are_allowlisted(self):
        response = Mock()
        response.status = 200
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock();opener.open.return_value = response
        with patch.object(oauth.urllib.request, 'build_opener', return_value=opener):
            for raw, category in ((b'mock-sensitive-not-json','json'),
                                  (json.dumps(dict(self.payload,tokenType='mock-sensitive')).encode(),'schema'),
                                  (b'{"code":403,"content":{"secret":"mock-sensitive"}}','schema'),
                                  (b'x'*65537,'json')):
                response.read.return_value=raw
                with self.subTest(category=category), self.assertRaises(oauth.TokenAPIError) as error:
                    oauth.post_token({'clientSecret':'mock-sensitive'})
                self.assertEqual(error.exception.category,category)
                self.assertEqual(error.exception.http_status,200)
                self.assertIn('HTTP 200',str(error.exception))
                self.assertNotIn('mock-sensitive',str(error.exception))
            for status in (400,401,403,429,500,302):
                body=io.BytesIO(b'mock-sensitive-response-body')
                opener.open.side_effect=urllib.error.HTTPError('https://mock-sensitive',status,'mock-sensitive-reason',{},body)
                with patch.object(body,'read',side_effect=AssertionError('must not read error body')):
                    with self.assertRaises(oauth.TokenAPIError) as error:oauth.post_token({})
                self.assertEqual(error.exception.diagnostic_code,'TOKEN_HTTP_'+str(status))
                self.assertIn('HTTP '+str(status),str(error.exception))
                self.assertNotIn('mock-sensitive',str(error.exception))

    def test_network_failures_never_expose_reason_or_partial_body(self):
        opener=Mock()
        for exception in (urllib.error.URLError('mock-sensitive-url'),TimeoutError('mock-sensitive-timeout'),
                          http.client.IncompleteRead(b'mock-sensitive-partial',42),OSError('mock-sensitive-network')):
            opener.open.side_effect=exception
            with patch.object(oauth.urllib.request,'build_opener',return_value=opener):
                with self.assertRaises(oauth.TokenAPIError) as error:oauth.post_token({})
            self.assertEqual(error.exception.category,'network')
            self.assertNotIn('mock-sensitive',str(error.exception))

    def test_callback_retains_safe_api_diagnostic_in_browser_and_terminal(self):
        failures=[oauth.TokenAPIError('http',status) for status in (400,401,403,429,500)]
        failures += [oauth.TokenAPIError('json',200),oauth.TokenAPIError('schema',200),oauth.TokenAPIError('network')]
        for failure in failures:
            failure.args=('mock-sensitive-original-exception',)
            request=Mock(side_effect=failure)
            def action(state):
                status,body,headers=self.callback('/callback?code=mock-sensitive-code&state='+state)
                self.assertEqual(status,502)
                self.assertIn(failure.diagnostic_code.encode(),body)
                self.assertNotIn(b'mock-sensitive',body)
                self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertEqual(headers['Referrer-Policy'],'no-referrer')
            with self.subTest(code=failure.diagnostic_code):
                errors,request=self.run_login(action,request=request)
                self.assertIsInstance(errors[0],oauth.TokenAPIError)
                self.assertEqual(errors[0].diagnostic_code,failure.diagnostic_code)
                self.assertNotIn('mock-sensitive',str(errors[0]))
                request.assert_called_once()
                self.assertFalse(self.store.path.exists())
                # The same sanitized error is exactly what main prints; no exception repr.
                output=io.StringIO()
                with patch.object(oauth,'TokenStore',return_value=self.store), \
                     patch.object(oauth,'credentials',return_value=('mock-client','mock-secret')), \
                     patch.object(oauth,'login',side_effect=errors[0]),contextlib.redirect_stdout(output):
                    self.assertEqual(oauth.main(['login']),1)
                self.assertIn(failure.diagnostic_code,output.getvalue())
                for secret in ('mock-sensitive','mock-client','mock-secret','mock-access-sensitive','mock-refresh-sensitive'):
                    self.assertNotIn(secret,output.getvalue())

    def test_unexpected_api_exception_cannot_escape_as_http_server_traceback(self):
        def action(state):
            status,body,_=self.callback('/callback?code=mock-sensitive-code&state='+state)
            self.assertEqual(status,502);self.assertIn(b'TOKEN_API_UNKNOWN',body)
            self.assertNotIn(b'mock-sensitive',body)
        errors,_=self.run_login(action,request=Mock(side_effect=RuntimeError('mock-sensitive-body')))
        self.assertEqual(errors[0].diagnostic_code,'TOKEN_API_UNKNOWN')
        self.assertNotIn('mock-sensitive',str(errors[0]))

    def test_callback_local_storage_error_is_distinct_from_api_error(self):
        for failure in (PermissionError('mock-sensitive-path'),OSError('mock-sensitive-disk'),
                        oauth.OAuthError('mock-sensitive-dpapi'),RuntimeError('mock-sensitive-unexpected-save')):
            def action(state):
                status,body,_=self.callback('/callback?code=mock-sensitive-code&state='+state)
                self.assertEqual(status,500)
                self.assertIn(b'LOCAL_TOKEN_SAVE',body)
                self.assertNotIn(b'mock-sensitive',body)
            with self.subTest(kind=type(failure).__name__),patch.object(self.store,'save',side_effect=failure):
                errors,request=self.run_login(action)
            self.assertIsInstance(errors[0],oauth.TokenStorageError)
            self.assertIn('LOCAL_TOKEN_SAVE',str(errors[0]))
            self.assertNotIn('mock-sensitive',str(errors[0]))
            request.assert_called_once()

    def test_refresh_save_and_status_read_errors_are_classified(self):
        self.store.save(self.tokens())
        before=self.store.path.read_bytes()
        request=Mock(return_value=dict(self.tokens(),refreshToken='new-refresh'))
        with patch.object(oauth.os,'replace',side_effect=OSError('mock-sensitive-path')):
            with self.assertRaises(oauth.TokenStorageError) as error:
                oauth.refresh_tokens('mock-client','mock-secret',self.store,force=True,request=request)
        self.assertEqual(error.exception.diagnostic_code,'LOCAL_TOKEN_SAVE')
        self.assertEqual(self.store.path.read_bytes(),before)
        request.assert_called_once()
        self.assertNotIn('mock-sensitive',str(error.exception))
        self.store.path.write_bytes(b'mock-sensitive-corrupt-file')
        output=io.StringIO()
        with patch.object(oauth,'TokenStore',return_value=self.store),contextlib.redirect_stdout(output):
            self.assertEqual(oauth.main(['status']),1)
        self.assertIn('LOCAL_TOKEN_READ',output.getvalue())
        self.assertNotIn('mock-sensitive',output.getvalue())

    def test_bad_api_return_is_not_misdiagnosed_as_storage_failure(self):
        def action(state):
            status,body,_=self.callback('/callback?code=mock-code&state='+state)
            self.assertEqual(status,502);self.assertIn(b'TOKEN_RESPONSE_SCHEMA',body)
        with patch.object(self.store,'save',side_effect=AssertionError('must not save invalid API response')):
            errors,_=self.run_login(action,request=Mock(return_value=['mock-sensitive']))
        self.assertEqual(errors[0].diagnostic_code,'TOKEN_RESPONSE_SCHEMA')

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI requires a Windows user session')
    def test_windows_dpapi(self):
        self.store.save(self.tokens())
        self.assertNotIn(b'mock-access-sensitive', self.store.path.read_bytes())
        self.assertEqual(self.store.load()['accessToken'], 'mock-access-sensitive')


if __name__ == '__main__':
    unittest.main()
