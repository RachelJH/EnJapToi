"""CHZZK Authorization Code helper. No donation subscription is performed.
Official contract: https://chzzk.gitbook.io/chzzk/chzzk-api/authorization
"""
import argparse
import contextlib
import ctypes
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

REDIRECT_URI = 'http://127.0.0.1:18766/callback'
AUTHORIZE_URL = 'https://chzzk.naver.com/account-interlock'
TOKEN_URL = 'https://openapi.chzzk.naver.com/auth/v1/token'
LOCAL = Path(__file__).resolve().parent / '.local'


class OAuthError(Exception):
    """Only fixed, public-safe messages may cross the CLI boundary."""


def credentials(config=None):
    values = {}
    if config is not None:
        try:
            values = json.loads(Path(config).read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                raise ValueError()
        except (OSError, ValueError):
            raise OAuthError('클라이언트 설정 파일을 읽을 수 없습니다.') from None
    client_id = os.environ.get('CHZZK_CLIENT_ID') or values.get('clientId')
    secret = os.environ.get('CHZZK_CLIENT_SECRET') or values.get('clientSecret')
    if not all(isinstance(v, str) and v.strip() for v in (client_id, secret)):
        raise OAuthError('Client ID와 Client Secret 설정이 필요합니다.')
    return client_id, secret


def dpapi(data, decrypt=False):
    """Windows current-user DPAPI; never fall back to plaintext on Windows."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), 'EnJapToi CHZZK tokens', None, None, None, 1,
                ctypes.byref(output))
    fn.restype = wintypes.BOOL
    if not fn(*args):
        raise OAuthError('Windows 사용자 보호 저장소 처리에 실패했습니다.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


class TokenStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else LOCAL / 'tokens.dat'

    def prepare(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt':
            os.chmod(self.path.parent, 0o700)

    @contextlib.contextmanager
    def lock(self):
        self.prepare()
        path = self.path.with_suffix(self.path.suffix + '.lock')
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise OAuthError('다른 인증 작업이 진행 중입니다. 남은 잠금 파일은 README를 확인하세요.') from None
        try:
            os.close(fd)
            yield
        finally:
            path.unlink(missing_ok=True)

    def save(self, tokens):
        self.prepare()
        data = json.dumps(tokens, ensure_ascii=False).encode('utf-8')
        if os.name == 'nt':
            data = b'DPAPI1\n' + dpapi(data)
        else:
            data = b'POSIX1\n' + data
        fd, name = tempfile.mkstemp(prefix='.tokens-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def load(self):
        try:
            data = self.path.read_bytes()
            if os.name == 'nt' and data.startswith(b'DPAPI1\n'):
                data = dpapi(data[7:], decrypt=True)
            elif os.name != 'nt' and data.startswith(b'POSIX1\n'):
                if self.path.stat().st_mode & 0o077:
                    raise OAuthError('토큰 파일 권한이 안전하지 않습니다. 소유자 전용으로 제한하세요.')
                data = data[7:]
            else:
                raise ValueError()
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (OSError, ValueError):
            raise OAuthError('저장된 인증 정보를 읽을 수 없습니다. 다시 로그인하세요.') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_token(body):
    req = urllib.request.Request(TOKEN_URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    # Default proxy/CA configuration is retained; credentials are never redirected.
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        code = e.code
        e.close()
        if code == 401:
            raise OAuthError('인증이 거부되었습니다. 설정 확인 후 다시 로그인하세요.') from None
        raise OAuthError(f'토큰 API 요청 실패 (HTTP {code}). 자동 재시도하지 않습니다.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OAuthError('토큰 API 통신 실패. 토큰 사용 여부가 불명확하므로 자동 재시도하지 않습니다.') from None
    except ValueError:
        raise OAuthError('토큰 API 응답 형식이 올바르지 않습니다.') from None
    return normalize_tokens(data)


def normalize_tokens(data):
    try:
        # Token documentation lists direct fields; accept the common API envelope too.
        if isinstance(data, dict) and 'content' in data:
            if data.get('code') != 200:
                raise ValueError()
            data = data['content']
        if not isinstance(data, dict) or data.get('tokenType') != 'Bearer':
            raise ValueError()
        if not all(isinstance(data.get(k), str) and data[k] for k in ('accessToken', 'refreshToken')):
            raise ValueError()
        ttl = int(data['expiresIn'])
        if ttl <= 0:
            raise ValueError()
        return {'accessToken': data['accessToken'], 'refreshToken': data['refreshToken'],
                'tokenType': 'Bearer', 'expiresAt': time.time() + ttl}
    except (ValueError, TypeError, KeyError, OverflowError):
        raise OAuthError('토큰 API 응답 형식이 올바르지 않습니다.') from None


def refresh_tokens(client_id, secret, store, force=False, request=post_token):
    # Refresh tokens are single-use. Hold lock across load, request and replacement.
    with store.lock():
        old = store.load()
        if old.get('clientId') != client_id:
            raise OAuthError('저장된 인증과 Client ID가 다릅니다. 다시 로그인하세요.')
        if not isinstance(old.get('refreshToken'), str) or not old['refreshToken']:
            raise OAuthError('갱신 토큰이 없습니다. 다시 로그인하세요.')
        expiry = old.get('expiresAt')
        if not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
            raise OAuthError('저장된 만료 정보가 올바르지 않습니다.')
        if not force and expiry > time.time() + 60:
            return old
        new = request({'grantType': 'refresh_token', 'clientId': client_id,
                       'clientSecret': secret, 'refreshToken': old['refreshToken']})
        new['clientId'] = client_id
        store.save(new)
        return new


class CallbackServer(HTTPServer):
    # POSIX: permit a fresh login after TIME_WAIT. Windows: prevent port sharing.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CallbackHandler(BaseHTTPRequestHandler):
    # Never log the request line: it contains the authorization code and state.
    def log_message(self, *args):
        pass

    def handle(self):
        self.connection.settimeout(2)
        try:
            super().handle()
        except (OSError, TimeoutError):
            pass

    def reply(self, status, text):
        data = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        s = self.server
        try:
            parsed = urllib.parse.urlsplit(self.path)
        except ValueError:
            self.reply(400, 'Invalid callback')
            return
        if parsed.path != '/callback' or len(self.path) > 8192:
            self.reply(404, 'Not found')
            return
        if self.headers.get('Host') != '127.0.0.1:18766':
            self.reply(400, 'Invalid callback host')
            return
        try:
            q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True, max_num_fields=10)
        except ValueError:
            self.reply(400, 'Invalid callback')
            return
        state = q.get('state', [])
        if len(state) != 1 or not hmac.compare_digest(state[0].encode(), s.state.encode()):
            self.reply(400, 'Invalid state. Authentication was not changed.')
            return
        if s.consumed or time.monotonic() >= s.deadline:
            self.reply(400, 'Expired callback')
            return
        if 'error' in q:
            s.consumed = True
            s.failure = OAuthError('브라우저 인증이 완료되지 않았습니다. 다시 로그인하세요.')
            self.reply(400, 'Authorization not completed. Close this tab.')
            return
        if len(q.get('code', [])) != 1 or not q['code'][0]:
            self.reply(400, 'Missing or invalid code')
            return
        s.consumed = True
        try:
            tokens = s.request_token({'grantType': 'authorization_code',
                                     'clientId': s.client_id, 'clientSecret': s.secret,
                                     'code': q['code'][0], 'state': s.state})
            tokens['clientId'] = s.client_id
            s.store.save(tokens)
        except (OAuthError, OSError):
            s.failure = OAuthError('토큰 발급 또는 안전한 저장에 실패했습니다. 다시 로그인하세요.')
            self.reply(502, 'Authentication failed. Close this tab and retry login.')
            return
        s.success = True
        self.reply(200, 'Authentication saved. Close this tab and return to the terminal.')


def login(client_id, secret, store, timeout=300, open_browser=webbrowser.open,
          request=post_token, ready=None):
    state = secrets.token_urlsafe(32)
    url = AUTHORIZE_URL + '?' + urllib.parse.urlencode(
        {'clientId': client_id, 'redirectUri': REDIRECT_URI, 'state': state})
    with store.lock():
        try:
            server = CallbackServer(('127.0.0.1', 18766), CallbackHandler)
        except OSError:
            raise OAuthError('127.0.0.1:18766을 사용할 수 없습니다. 다른 인증 도구를 종료하세요.') from None
        with server:
            server.state, server.client_id, server.secret = state, client_id, secret
            server.store, server.request_token = store, request
            server.consumed, server.success, server.failure = False, False, None
            server.deadline = time.monotonic() + timeout
            server.timeout = min(0.5, timeout)
            # Server is bound before browser launch. Do not print credential-bearing URLs.
            try:
                if not open_browser(url):
                    raise OAuthError('브라우저를 열 수 없습니다. 브라우저가 있는 Windows PC에서 실행하세요.')
                if ready:
                    ready(server)  # Test hook; never used by CLI.
                while not server.consumed and time.monotonic() < server.deadline:
                    server.handle_request()
            finally:
                server.secret = None
                server.state = ''
            if server.failure:
                raise server.failure
            if not server.success:
                raise OAuthError('인증 대기 시간이 만료되었습니다. 다시 로그인하세요.')


def main(argv=None):
    ap = argparse.ArgumentParser(description='EnJapToi CHZZK OAuth (no donation receiver)')
    ap.add_argument('command', choices=['login', 'refresh', 'status'])
    ap.add_argument('--config', type=Path, help='Local JSON with clientId/clientSecret (never commit)')
    args = ap.parse_args(argv)
    store = TokenStore()
    try:
        if args.command == 'status':
            with store.lock():
                data = store.load()
            expiry = data.get('expiresAt', 0)
            if not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
                raise OAuthError('저장된 만료 정보가 올바르지 않습니다.')
            print('로컬 인증 저장됨. 갱신 필요 여부:', '필요' if expiry <= time.time() + 60 else '아직 아님')
            print('서버 측 유효성·계정·Scope는 이 명령으로 검증하지 않습니다.')
        else:
            client_id, secret = credentials(args.config)
            if args.command == 'login':
                print('브라우저에서 방송인 계정과 권한을 확인하세요. 최대 5분간 기다립니다.')
                login(client_id, secret, store)
                print('인증 정보가 안전하게 저장되었습니다.')
            else:
                refresh_tokens(client_id, secret, store, force=True)
                print('인증 정보 갱신 및 교체 저장이 완료되었습니다.')
        return 0
    except OAuthError as e:
        print(str(e))
        return 1
    except (OSError, ValueError, RuntimeError):
        print('로컬 인증 처리에 실패했습니다. 파일 권한·저장 공간·브라우저 설정을 확인하세요.')
        return 1
    except KeyboardInterrupt:
        print('인증 작업을 취소했습니다.')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
