"""CHZZK Authorization Code helper. No donation subscription is performed.
Official contract: https://chzzk.gitbook.io/chzzk/chzzk-api/authorization
"""
import argparse
import contextlib
import ctypes
import hmac
import http.client
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
# Official Error Message values for HTTP 401, not arbitrary response text.
TOKEN_401_CODES = frozenset({'INVALID_CLIENT', 'UNAUTHORIZED', 'INVALID_TOKEN'})
ERROR_BODY_LIMIT = 4096


class OAuthError(Exception):
    """Only fixed, public-safe messages may cross the CLI boundary."""


class TokenAPIError(OAuthError):
    """Only an allowlisted category and numeric HTTP status may be displayed."""
    MESSAGES = {
        'http': ('TOKEN_HTTP', '토큰 API HTTP 요청 실패'),
        'json': ('TOKEN_RESPONSE_JSON', '토큰 API 응답 JSON 해석·크기 검증 실패'),
        'schema': ('TOKEN_RESPONSE_SCHEMA', '토큰 API 응답 필드·타입·값이 명세와 다릅니다'),
        'network': ('TOKEN_NETWORK', '토큰 API 네트워크 통신 실패'),
        'unknown': ('TOKEN_API_UNKNOWN', '토큰 발급 처리 실패 (안전하게 분류할 수 없는 오류)'),
    }

    def __init__(self, category, http_status=None, api_code=None):
        self.category = category if isinstance(category, str) and category in self.MESSAGES else 'unknown'
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.api_code = api_code if (self.category == 'http' and self.http_status == 401
                                    and isinstance(api_code, str) and api_code in TOKEN_401_CODES) else None
        code, message = self.MESSAGES[self.category]
        self.diagnostic_code = code + (f'_{self.http_status}' if self.category == 'http' and self.http_status is not None else '')
        status = f' (HTTP {self.http_status})' if self.http_status is not None else ''
        api = f' / API {self.api_code}' if self.api_code else (' / 공식 오류 코드 확인 불가' if self.category == 'http' and self.http_status == 401 else '')
        super().__init__(f'[{self.diagnostic_code}] {message}{status}{api}. 자동 재시도하지 않습니다. 설정 확인 후 다시 로그인하세요.')


class TokenStorageError(OAuthError):
    def __init__(self, operation):
        self.diagnostic_code = 'LOCAL_TOKEN_READ' if operation == 'read' else 'LOCAL_TOKEN_SAVE'
        action = '읽기·복호화' if operation == 'read' else '암호화·저장'
        super().__init__(f'[{self.diagnostic_code}] 로컬 토큰 {action} 실패. 파일 권한·저장 공간·Windows 사용자를 확인하고 다시 로그인하세요.')


def save_tokens(store, tokens):
    try:
        store.save(tokens)
    except Exception:
        raise TokenStorageError('save') from None


def load_tokens(store):
    try:
        return store.load()
    except Exception:
        raise TokenStorageError('read') from None


def credentials(config=None):
    values = {}
    if config is not None:
        try:
            values = json.loads(Path(config).read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                raise ValueError()
        except (OSError, ValueError):
            raise OAuthError('클라이언트 설정 파일을 읽을 수 없습니다.') from None
    env_id = os.environ.get('CHZZK_CLIENT_ID')
    env_secret = os.environ.get('CHZZK_CLIENT_SECRET')
    if env_id is not None or env_secret is not None:
        if not all(isinstance(v, str) and v.strip() for v in (env_id, env_secret)):
            raise OAuthError('[CLIENT_CONFIG_PAIR] 환경변수의 Client ID와 Secret을 둘 다 설정하거나 둘 다 제거하고 설정 파일을 사용하세요. 서로 다른 출처를 혼합하지 않습니다.')
        client_id, secret = env_id, env_secret
    else:
        client_id, secret = values.get('clientId'), values.get('clientSecret')
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
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b'0')
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            os.close(fd)
            raise OAuthError('다른 인증 작업이 진행 중입니다. 잠금 파일은 삭제하지 마세요.') from None
        try:
            yield
        finally:
            if locked:
                if os.name == 'nt':
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

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


def allowed_401_code(error):
    """Inspect a bounded error body in memory; return only an exact allowlist member."""
    if type(error.code) is not int or error.code != 401:
        return None
    try:
        raw = error.read(ERROR_BODY_LIMIT + 1)
        if len(raw) > ERROR_BODY_LIMIT:
            return None
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        body = json.loads(raw, object_pairs_hook=unique)
        message = body.get('message') if isinstance(body, dict) else None
        return message if isinstance(message, str) and message in TOKEN_401_CODES else None
    except Exception:
        # Malformed/oversized/partial/proxy error responses never reach diagnostics.
        return None


def post_token(body):
    req = urllib.request.Request(TOKEN_URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    # Default proxy/CA configuration is retained; credentials are never redirected.
    status = None
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            status = response.status
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            api_code = allowed_401_code(e)
        finally:
            e.close()
        raise TokenAPIError('http', code, api_code) from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise TokenAPIError('network', status) from None
    except ValueError:
        raise TokenAPIError('json', status) from None
    except Exception:
        raise TokenAPIError('unknown', status) from None
    return normalize_tokens(data, http_status=status)


def normalize_tokens(data, http_status=None):
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
        raise TokenAPIError('schema', http_status) from None


def refresh_tokens(client_id, secret, store, force=False, request=post_token):
    # Refresh tokens are single-use. Hold lock across load, request and replacement.
    with store.lock():
        old = load_tokens(store)
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
        save_tokens(store, new)
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
            if not isinstance(tokens, dict):
                raise TokenAPIError('schema')
        except TokenAPIError as error:
            # Reconstruct from allowlisted metadata; never propagate exception text.
            s.failure = TokenAPIError(error.category, error.http_status, error.api_code)
        except urllib.error.HTTPError as error:
            code = error.code
            try:
                api_code = allowed_401_code(error)
            finally:
                error.close()
            s.failure = TokenAPIError('http', code, api_code)
        except (OSError, http.client.HTTPException):
            s.failure = TokenAPIError('network')
        except (ValueError, TypeError):
            s.failure = TokenAPIError('schema')
        except OAuthError:
            s.failure = TokenAPIError('unknown')
        except Exception:
            # BaseHTTPRequestHandler must not print a raw unexpected exception.
            s.failure = TokenAPIError('unknown')
        if s.failure:
            api = f'; API {s.failure.api_code}' if s.failure.api_code else ''
            self.reply(502, f'Authentication failed [{s.failure.diagnostic_code}{api}]. Return to the terminal.')
            return
        try:
            tokens['clientId'] = s.client_id
            save_tokens(s.store, tokens)
        except (TokenStorageError, OSError, ValueError, TypeError):
            s.failure = TokenStorageError('save')
            self.reply(500, 'Authentication failed [LOCAL_TOKEN_SAVE]. Return to the terminal.')
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
                data = load_tokens(store)
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
        print('[LOCAL_OPERATION] 로컬 인증 처리에 실패했습니다. 파일 권한·저장 공간·브라우저 설정을 확인하세요.')
        return 1
    except KeyboardInterrupt:
        print('인증 작업을 취소했습니다.')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
