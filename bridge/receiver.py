"""Official CHZZK DONATION -> durable local outbox -> existing Paper bridge.
Contract: https://chzzk.gitbook.io/chzzk/chzzk-api/session
No upstream donation ID, replay or exactly-once guarantee is assumed.
"""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

if __package__:
    from . import oauth, bridge
else:
    import oauth
    import bridge


class ReceiverError(Exception):
    """Public-safe, fixed diagnostic only."""


class TransientError(ReceiverError):
    pass


def object_message(value):
    if isinstance(value, str):
        if len(value) > 65536:
            raise ReceiverError('이벤트 크기 제한을 초과했습니다.')
        try:
            value = json.loads(value)
        except ValueError:
            raise ReceiverError('이벤트 형식이 올바르지 않습니다.') from None
    if not isinstance(value, dict):
        raise ReceiverError('이벤트 형식이 올바르지 않습니다.')
    return value


def amount_map(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_keys)
        if not isinstance(value, dict):
            raise ValueError()
        for key, target in value.items():
            if not re.fullmatch(r'[1-9][0-9]{0,11}', key):
                raise ValueError()
            if type(target) is not int or target not in (1000, 2000, 5000, 30000):
                raise ValueError()
        return value  # Empty mapping is intentional observe-only mode.
    except (OSError, ValueError, TypeError):
        raise ReceiverError('금액 매핑 파일이 올바르지 않습니다.') from None


class Journal:
    """No raw message, amount, channel or donor PII is persisted."""
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt':
            os.chmod(path.parent, 0o700)
        # Create the database with restrictive mode before SQLite opens it.
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if os.name != 'nt':
            os.chmod(path, 0o600)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('''CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, effect TEXT, status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0)''')
        self.db.commit()

    def add(self, effect):
        event_id = secrets.token_urlsafe(24)
        with self.lock, self.db:
            self.db.execute('INSERT INTO events(id,effect,status) VALUES(?,?,?)',
                            (event_id, effect, 'pending' if effect else 'ignored'))
        return event_id

    def pending(self):
        with self.lock:
            return self.db.execute("SELECT id,effect,attempts,retry_at FROM events WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()

    def done(self, event_id):
        with self.lock, self.db:
            self.db.execute("UPDATE events SET status='done' WHERE id=?", (event_id,))

    def retry(self, event_id, attempts, now):
        with self.lock, self.db:
            self.db.execute('UPDATE events SET attempts=?,retry_at=? WHERE id=?',
                            (attempts, now + min(60, 2 ** min(attempts, 6)), event_id))

    def counts(self):
        with self.lock:
            return dict(self.db.execute('SELECT status,count(*) FROM events GROUP BY status'))

    def bind_channel(self, channel):
        digest = hashlib.sha256(channel.encode()).hexdigest()
        with self.lock, self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS context (channel_hash TEXT NOT NULL)')
            row = self.db.execute('SELECT channel_hash FROM context').fetchone()
            if row and row[0] != digest:
                raise ReceiverError('수신함의 대상 채널이 다릅니다. 기존 대기열을 먼저 처리하세요.')
            if not row:
                self.db.execute('INSERT INTO context VALUES(?)', (digest,))

    def close(self):
        self.db.close()


class Intake:
    def __init__(self, journal, channel, mapping, donation_type='CHAT'):
        self.journal, self.channel, self.mapping = journal, channel, mapping
        self.donation_type = donation_type

    def receive(self, payload):
        data = object_message(payload)
        if data.get('channelId') != self.channel:
            return False
        amount = data.get('payAmount')
        text = data.get('donationText')
        if (data.get('donationType') != self.donation_type or
                not isinstance(amount, str) or not re.fullmatch(r'[1-9][0-9]{0,11}', amount) or
                not isinstance(text, str) or len(text) > 16384):
            self.journal.add(None)
            return False
        target = self.mapping.get(amount)
        effect = bridge.select_event(target, text) if target is not None else None
        # Choose roulette exactly once, then persist BEFORE any Paper request.
        self.journal.add(effect)
        return effect is not None


def deliver_one(journal, token_file, port=18765, now=None, send=bridge.deliver):
    now = time.time() if now is None else now
    row = journal.pending()
    if row is None or row[3] > now:
        return None
    event_id, effect, attempts, _ = row
    try:
        token = Path(token_file).read_text(encoding='utf-8').strip()
        if not token:
            raise OSError()
        result = send(effect, event_id, token, port)
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        journal.retry(event_id, attempts + 1, now)
        return 'retry'
    if result in ('queued', 'duplicate'):
        # Crash after Paper accepted but before this commit -> SAME ID on restart.
        journal.done(event_id)
        return result
    journal.retry(event_id, attempts + 1, now)
    return 'retry'


class Tokens:
    def __init__(self, client_id, secret, store):
        self.client_id, self.secret, self.store = client_id, secret, store
        self.expires_at = 0

    def get(self, force=False):
        data = oauth.refresh_tokens(self.client_id, self.secret, self.store, force=force)
        token = data.get('accessToken')
        if not isinstance(token, str) or not token:
            raise oauth.OAuthError('저장된 액세스 토큰이 올바르지 않습니다. 다시 로그인하세요.')
        self.expires_at = data['expiresAt']
        return token


class Api:
    ROOT = 'https://openapi.chzzk.naver.com'

    def __init__(self, tokens):
        self.tokens = tokens

    def call(self, path, params=None):
        method = 'POST' if params is not None else 'GET'
        url = self.ROOT + path
        if params is not None:
            url += '?' + urllib.parse.urlencode(params)
        for attempt in range(2):
            token = self.tokens.get(force=attempt == 1)
            req = urllib.request.Request(url, method=method, data=b'' if params is not None else None,
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            try:
                with urllib.request.build_opener(oauth.NoRedirect()).open(req, timeout=20) as response:
                    raw = response.read(65537)
                    if len(raw) > 65536:
                        raise ValueError()
                    body = json.loads(raw)
                if not isinstance(body, dict) or body.get('code') != 200:
                    raise ValueError()
                return body.get('content')
            except urllib.error.HTTPError as e:
                code = e.code
                e.close()
                if code == 401 and attempt == 0:
                    continue  # Only one forced refresh, with the OAuth file lock.
                if code == 429 or code >= 500:
                    raise TransientError('공식 API 일시 오류. 새 세션으로 재시도합니다.') from None
                raise ReceiverError('공식 API 인증·권한·요청이 거부됐습니다. 계정과 Scope를 확인하세요.') from None
            except (urllib.error.URLError, TimeoutError, OSError):
                raise TransientError('공식 API 통신 실패. 새 세션으로 재시도합니다.') from None
            except (ValueError, TypeError):
                raise ReceiverError('공식 API 응답 형식이 올바르지 않습니다.') from None

    def verify_channel(self, expected):
        data = self.call('/open/v1/users/me')
        if not isinstance(data, dict) or data.get('channelId') != expected:
            raise ReceiverError('인증 계정과 대상 채널이 다릅니다. 방송인 계정으로 다시 로그인하세요.')

    def session(self):
        data = self.call('/open/v1/sessions/auth')
        url = data.get('url') if isinstance(data, dict) else None
        try:
            p = urllib.parse.urlsplit(url) if isinstance(url, str) else None
            if (p is None or p.scheme != 'https' or not p.hostname or p.port not in (None, 443)
                    or p.username or p.password or p.fragment):
                raise ValueError()
        except ValueError:
            raise ReceiverError('공식 API의 소켓 URL이 올바르지 않습니다.') from None
        return url

    def subscribe(self, key):
        self.call('/open/v1/sessions/events/subscribe/donation', {'sessionKey': key})


def socket_client():
    import socketio
    import engineio
    import websocket

    class OrderedEngineIO(engineio.Client):
        def _trigger_event(self, event, *args, **kwargs):
            # Engine.IO 3.14.2 otherwise dispatches each message in a new thread.
            # Keep wire order and finish durable receipt before reading the next.
            if event == 'message':
                kwargs['run_async'] = False
            return super()._trigger_event(event, *args, **kwargs)

    class OrderedSocketIO(socketio.Client):
        def _engineio_client_class(self):
            return OrderedEngineIO
    # logger=False still logs fatal errors in these versions. Use a silent logger.
    silent = logging.Logger('enjaptoi-private-socket')
    silent.addHandler(logging.NullHandler())
    silent.propagate = False
    websocket.enableTrace(False)
    wire_log = logging.getLogger('websocket')
    wire_log.handlers = [logging.NullHandler()]
    wire_log.propagate = False
    if not os.environ.get('WEBSOCKET_CLIENT_CA_BUNDLE'):
        ca = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
        if ca:
            os.environ['WEBSOCKET_CLIENT_CA_BUNDLE'] = ca
    websocket.setdefaulttimeout(10)
    return OrderedSocketIO(reconnection=False, logger=silent, engineio_logger=silent,
                           request_timeout=10, ssl_verify=True)


class Session:
    """One fresh Socket.IO connection. No REST calls in socket callbacks."""
    def __init__(self, api, intake, factory=socket_client, clock=time.monotonic):
        self.api, self.intake, self.clock = api, intake, clock
        self.client = factory()
        self.events = queue.Queue(maxsize=100)
        self.deadline = clock() + 30
        self.accepting = False
        self.subscribed = False
        self.closed = False
        self.key = None
        self.failure = None
        self.guard = threading.RLock()
        self.client.on('SYSTEM', self.system)
        self.client.on('DONATION', self.donation)
        self.client.on('disconnect', self.disconnected)

    def fail(self, error):
        with self.guard:
            if self.closed:
                return
            self.accepting = False
            # Storage/protocol/revocation errors must survive later disconnects.
            if self.failure is None or (isinstance(self.failure, TransientError)
                                        and not isinstance(error, TransientError)):
                self.failure = error

    def check_failure(self):
        with self.guard:
            if self.failure:
                raise self.failure

    def check_fatal(self):
        with self.guard:
            if self.failure and not isinstance(self.failure, TransientError):
                raise self.failure

    def system(self, payload):
        if self.closed:
            return
        try:
            event = object_message(payload)
            data = event.get('data')
            if (event.get('type') in ('revoked', 'unsubscribed') and isinstance(data, dict)
                    and data.get('eventType') == 'DONATION' and data.get('channelId') == self.intake.channel):
                self.fail(ReceiverError('후원 구독 권한이 취소됐습니다. 권한을 확인하고 다시 시작하세요.'))
            self.events.put_nowait(event)
        except (ReceiverError, queue.Full):
            self.fail(ReceiverError('시스템 이벤트 처리 실패. 수신을 중단합니다.'))

    def disconnected(self):
        self.fail(TransientError('연결이 끊겼습니다. 새 세션을 생성합니다.'))

    def donation(self, payload):
        with self.guard:
            if self.closed or not self.accepting:
                return
            try:
                self.intake.receive(payload)
            except ReceiverError:
                self.fail(ReceiverError('후원 메시지 형식이 올바르지 않습니다. 수신을 중단합니다.'))
            except Exception:
                # Fail closed on disk/storage failure; no unpersisted delivery.
                self.fail(ReceiverError('수신 이벤트 저장 실패. 수신을 중단합니다.'))

    def connect(self):
        url = self.api.session()
        try:
            self.client.connect(url, transports=['websocket'])
        except Exception:
            self.check_failure()
            raise TransientError('소켓 연결 실패. 새 세션을 생성합니다.') from None

    def step(self):
        self.check_failure()
        while not self.events.empty():
            self.check_failure()
            event = self.events.get_nowait()
            data = event.get('data')
            if not isinstance(data, dict):
                raise ReceiverError('시스템 메시지 형식이 올바르지 않습니다.')
            kind = event.get('type')
            if kind == 'connected':
                key = data.get('sessionKey')
                if not isinstance(key, str) or not key or len(key) > 4096:
                    raise ReceiverError('세션 키 형식이 올바르지 않습니다.')
                if self.key is not None:
                    if self.key != key:
                        raise TransientError('세션 키가 변경됐습니다. 새 세션을 생성합니다.')
                    continue
                with self.guard:
                    self.check_failure()
                    self.key = key
                    self.accepting = True
                try:
                    self.api.subscribe(key)
                except (ReceiverError, oauth.OAuthError) as error:
                    self.fail(error)
                    self.check_failure()
                self.check_failure()
            elif data.get('eventType') == 'DONATION' and data.get('channelId') == self.intake.channel:
                if kind == 'subscribed':
                    if self.key is None or not self.accepting:
                        raise ReceiverError('요청하지 않은 후원 구독 확인을 받았습니다.')
                    self.subscribed = True
                elif kind in ('revoked', 'unsubscribed'):
                    self.accepting = False
                    raise ReceiverError('후원 구독 권한이 취소됐습니다. 권한을 확인하고 다시 시작하세요.')
        self.check_failure()
        if not self.subscribed and self.clock() >= self.deadline:
            raise TransientError('후원 구독 확인 시간 초과. 새 세션을 생성합니다.')

    def close(self):
        with self.guard:
            self.closed = True
            self.accepting = False
        try:
            self.client.disconnect()
        except Exception:
            pass  # Never print socket exceptions containing auth URLs.


def run(api, intake, journal, token_file, port=18765, stop=None,
        factory=socket_client, tick=0.5):
    stop = stop or threading.Event()
    session = None
    retry_at = 0
    failures = 0
    report_at = 0
    verified = False
    announced = False
    try:
        while not stop.is_set():
            now = time.monotonic()
            try:
                if not verified and now >= retry_at:
                    api.verify_channel(intake.channel)
                    verified = True
                if session is None and now >= retry_at:
                    session = Session(api, intake, factory)
                    announced = False
                    session.connect()
                if session is not None:
                    session.step()
                    if session.subscribed:
                        failures = 0
                        if not announced:
                            print('공식 후원 구독 확인 완료.')
                            announced = True
                    # Proactive renewal via a fresh session; old URL is never reused.
                    if time.time() + 60 >= api.tokens.expires_at:
                        session.close()
                        session.check_fatal()
                        session = None
                        retry_at = now
                    if session:
                        session.check_failure()
            except TransientError as e:
                if session:
                    session.close()
                    session.check_fatal()
                print(str(e))  # Fixed messages only, never exception repr/response.
                session = None
                failures += 1
                retry_at = now + min(60, 2 ** min(failures, 6))
            result = deliver_one(journal, token_file, port)
            if result is not None:
                print('Paper 전달:', result)  # No token, donor, text or raw payload.
            if now >= report_at:
                counts = journal.counts()
                print('수신함 집계:', '대기', counts.get('pending', 0),
                      '완료', counts.get('done', 0), '제외', counts.get('ignored', 0))
                report_at = now + 60
            stop.wait(tick)
    finally:
        if session:
            session.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description='Official CHZZK donation receiver; no upstream replay guarantee')
    ap.add_argument('--config', type=Path)
    ap.add_argument('--channel-id', required=True, help='Authorized broadcaster channel ID (not nickname)')
    ap.add_argument('--amount-map', type=Path, required=True, help='Explicit KRW-string -> existing game amount JSON; {} observes only')
    ap.add_argument('--donation-type', choices=['CHAT', 'VIDEO'], default='CHAT')
    ap.add_argument('--token-file', type=Path, required=True, help='Paper bridge-token.txt; never print contents')
    ap.add_argument('--port', type=int, default=18765)
    args = ap.parse_args(argv)
    journal = None
    try:
        if not args.channel_id or len(args.channel_id) > 128 or not 1 <= args.port <= 65535:
            raise ReceiverError('채널 또는 포트 설정이 올바르지 않습니다.')
        mapping = amount_map(args.amount_map)
        client_id, secret = oauth.credentials(args.config)
        import socketio  # Fail before entering reconnect loop when dependencies are missing.
        del socketio
        # A separate process lock prevents two receivers duplicating the same stream/outbox.
        with oauth.TokenStore(oauth.LOCAL / 'receiver').lock():
            journal = Journal(oauth.LOCAL / 'donations.sqlite3')
            journal.bind_channel(args.channel_id)
            intake = Intake(journal, args.channel_id, mapping, args.donation_type)
            print('후원 수신 시작. 금액 매핑은 사용자 설정이며 치즈 대응 검증 결과가 아닙니다.')
            if not mapping:
                print('관찰 모드: 새 후원은 게임에 전달하지 않습니다. 기존 미전달 이벤트는 재시도합니다.')
            run(Api(Tokens(client_id, secret, oauth.TokenStore())), intake, journal, args.token_file, args.port)
    except (ReceiverError, oauth.OAuthError) as e:
        print(str(e))
        return 1
    except KeyboardInterrupt:
        print('수신 종료. 저장된 미전달 이벤트는 다음 실행에서 재시도합니다.')
        return 0
    except ImportError:
        print('가상환경에 bridge/requirements.txt 의존성을 설치하세요.')
        return 1
    except Exception:
        print('로컬 수신 처리 실패. 파일 권한·저장 공간·설정을 확인하세요. 비밀정보가 포함될 수 있는 원본 오류는 출력하지 않습니다.')
        return 1
    finally:
        if journal:
            journal.close()


if __name__ == '__main__':
    raise SystemExit(main())
