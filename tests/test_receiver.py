import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from bridge import receiver as r
from bridge import oauth


class FakeSocket:
    def __init__(self): self.handlers = {}; self.closed = False
    def on(self, name, handler): self.handlers[name] = handler
    def connect(self, url, transports):
        self.url = url
        self.transports = transports
        self.handlers['SYSTEM']({'type':'connected','data':{'sessionKey':'key'}})
    def disconnect(self):
        self.closed = True
        self.handlers['disconnect']()


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'private' / 'inbox.sqlite3'
        self.journal = r.Journal(self.path)
        self.addCleanup(lambda: self.journal.close())
        self.intake = r.Intake(self.journal, 'channel', {'1000':1000}, allow_game_events=True)
        self.payload = {'channelId':'channel','donationType':'CHAT','payAmount':'1000',
                        'donationText':'!밥 secret-message','donatorNickname':'secret-nickname',
                        'donatorChannelId':'secret-donor'}
        self.token = Path(self.tmp.name) / 'token'
        self.token.write_text('secret-paper-token')

    def test_explicit_amount_mapping(self):
        p = Path(self.tmp.name) / 'map.json'
        for obj in ({}, {'100':1000}):
            p.write_text(json.dumps(obj)); self.assertEqual(r.amount_map(p), obj)
        for obj in ({'1000':True}, {'1.0':1000}, {'01':1000}, {'1000':999}, []):
            p.write_text(json.dumps(obj))
            with self.assertRaises(r.ReceiverError): r.amount_map(p)
        self.assertFalse(r.Intake(self.journal, 'channel', {}).receive(self.payload))
        self.assertEqual(self.journal.counts(), {'ignored':1})

    @patch.object(r.bridge.secrets,"choice",return_value="bread")
    def test_intake_no_pii_and_no_fake_upstream_dedup(self, choice):
        self.assertTrue(self.intake.receive(json.dumps(self.payload)))
        self.assertTrue(self.intake.receive(self.payload))
        rows = self.journal.db.execute('SELECT id,effect,status FROM events').fetchall()
        self.assertNotEqual(rows[0][0], rows[1][0])
        self.assertEqual([x[1] for x in rows], ['bread','bread'])
        for file in self.path.parent.iterdir():
            raw = file.read_bytes()
            self.assertNotIn(b'secret-', raw)
            self.assertNotIn(b'!\xeb\xb0\xa5', raw)
        if os.name != 'nt': self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.journal.bind_channel('channel')
        self.journal.bind_channel('channel')
        with self.assertRaises(r.ReceiverError): self.journal.bind_channel('another-channel')

    def test_invalid_type_channel_amount_and_message(self):
        self.assertFalse(self.intake.receive(dict(self.payload, channelId='other')))
        for change in ({'payAmount':1000}, {'payAmount':'1,000'}, {'payAmount':'1000.0'},
                       {'donationText':None}, {'donationType':'VIDEO'}, {'payAmount':'2000'}):
            self.assertFalse(self.intake.receive(dict(self.payload, **change)))
        self.assertIsNone(self.journal.pending())
        with self.assertRaises(r.ReceiverError): self.intake.receive('{private-invalid')

    def test_retry_persists_same_id_effect_and_roulette(self):
        with patch.object(r.bridge, 'select_event', return_value='buff') as selector:
            self.intake.receive(dict(self.payload, donationText='roulette'))
            before = self.journal.pending()
            self.assertEqual(r.deliver_one(self.journal,self.token,now=10,
                send=Mock(side_effect=OSError('secret-transport'))), 'retry')
            selector.assert_called_once()
        # Close/reopen like a process restart; no second random selection.
        self.journal.close(); self.journal = r.Journal(self.path)
        self.assertEqual(self.journal.pending()[:2], before[:2])
        send = Mock(return_value='duplicate')
        self.assertIsNone(r.deliver_one(self.journal,self.token,now=11,send=send))
        self.assertEqual(r.deliver_one(self.journal,self.token,now=13,send=send), 'duplicate')
        self.assertEqual(send.call_args.args[:2], ('buff',before[0]))
        self.assertEqual(self.journal.counts(), {'done':1})

    def test_ack_lost_or_crash_before_local_commit(self):
        self.intake.receive(self.payload)
        accepted = set()
        def paper(effect, event_id, token, port):
            if event_id in accepted: return 'duplicate'
            accepted.add(event_id); return 'queued'
        with patch.object(self.journal,'done',side_effect=sqlite3.OperationalError('disk-full')):
            with self.assertRaises(sqlite3.OperationalError):
                r.deliver_one(self.journal,self.token,send=paper)
        self.journal.close();self.journal = r.Journal(self.path)
        self.assertEqual(r.deliver_one(self.journal,self.token,send=paper),'duplicate')
        self.assertEqual(len(accepted),1)

    def test_missing_token_and_unexpected_paper_response_retry(self):
        self.intake.receive(self.payload)
        self.token.unlink()
        send = Mock()
        self.assertEqual(r.deliver_one(self.journal,self.token,now=10,send=send),'retry')
        send.assert_not_called()
        self.token.write_text('secret-paper-token')
        send.return_value='not-queued'
        self.assertEqual(r.deliver_one(self.journal,self.token,now=20,send=send),'retry')
        self.assertEqual(self.journal.counts(),{'pending':1})

    def test_session_subscribe_timeout_revoke_and_stale_callback(self):
        socket = FakeSocket(); api = Mock();api.session.return_value='https://socket.example?auth=secret'
        session = r.Session(api,self.intake,lambda:socket,clock=lambda:0)
        session.connect();session.step()
        api.subscribe.assert_called_once_with('key')
        self.assertEqual(socket.transports,['websocket'])
        socket.handlers['SYSTEM']({'type':'subscribed','data':{'channelId':'channel','eventType':'DONATION'}})
        session.step();self.assertTrue(session.subscribed)
        socket.handlers['DONATION'](self.payload)
        socket.handlers['SYSTEM']({'type':'revoked','data':{'channelId':'channel','eventType':'DONATION'}})
        with self.assertRaises(r.ReceiverError):session.step()
        session.close();socket.handlers['DONATION'](self.payload)
        self.assertEqual(self.journal.counts(),{'pending':1})
        clock=Mock(return_value=0);s=r.Session(api,self.intake,FakeSocket,clock)
        clock.return_value=31
        with self.assertRaises(r.TransientError):s.step()
        s.close()

    def test_storage_failure_stops_session_before_delivery(self):
        s=r.Session(Mock(),self.intake,FakeSocket);s.accepting=True
        with patch.object(self.journal,'add',side_effect=sqlite3.OperationalError('secret-path')):
            s.donation(self.payload)
        with self.assertRaises(r.ReceiverError) as error:s.step()
        self.assertNotIn('secret',str(error.exception));self.assertIsNone(self.journal.pending())
        s.close()

    def test_api_401_refresh_once_and_sanitized_error(self):
        tokens=Mock();tokens.get.side_effect=['old-token','new-token']
        api=r.Api(tokens)
        response=Mock();response.read.return_value=b'{"code":200,"content":{"ok":true}}'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.side_effect=[urllib.error.HTTPError('secret-url',401,'secret',{},io.BytesIO()),response]
        with patch.object(r.urllib.request,'build_opener',return_value=opener):
            self.assertEqual(api.call('/test'),{'ok':True})
        self.assertEqual([c.kwargs for c in tokens.get.call_args_list],[{'force':False},{'force':True}])
        req=opener.open.call_args.args[0];self.assertEqual(req.get_header('Authorization'),'Bearer new-token')
        for code in (403,429,500):
            tokens.get.side_effect=None;tokens.get.return_value='secret-token'
            opener.open.side_effect=urllib.error.HTTPError('secret-url',code,'secret-body',{},io.BytesIO())
            with patch.object(r.urllib.request,'build_opener',return_value=opener):
                with self.assertRaises(r.ReceiverError) as error:api.call('/test')
                self.assertNotIn('secret',str(error.exception))

    def test_api_query_contract_and_https_only(self):
        api=r.Api(Mock());api.call=Mock(return_value={'url':'https://ssio08.nchat.naver.com?auth=secret'})
        self.assertTrue(api.session().startswith('https:'))
        api.subscribe('private-key')
        api.call.assert_called_with('/open/v1/sessions/events/subscribe/donation',{'sessionKey':'private-key'})
        for url in ('http://127.0.0.1', 'https://user:pass@host', 'https://host:80', 'file:///tmp/token'):
            api.call.return_value={'url':url}
            with self.assertRaises(r.ReceiverError):api.session()
        api.call.return_value={'channelId':'wrong'}
        with self.assertRaises(r.ReceiverError):api.verify_channel('expected')

    def test_tokens_reuse_oauth_refresh(self):
        store=Mock();source=r.Tokens('client','secret',store)
        with patch.object(oauth,'refresh_tokens',return_value={'accessToken':'new','expiresAt':999}) as refresh:
            self.assertEqual(source.get(force=True),'new')
            refresh.assert_called_once_with('client','secret',store,force=True)
            self.assertEqual(source.expires_at,999)

    def test_expired_token_rotation_persists_and_failure_stops(self):
        store = oauth.TokenStore(Path(self.tmp.name)/'oauth/tokens.dat')
        store.save({'clientId':'client','accessToken':'old','refreshToken':'old-refresh','expiresAt':0})
        source = r.Tokens('client','secret',store)
        real_refresh = oauth.refresh_tokens
        request = Mock(return_value={'accessToken':'new','refreshToken':'new-refresh',
                                    'expiresAt':time.time()+86400,'tokenType':'Bearer'})
        def refresh(*args, **kwargs):
            return real_refresh(*args, **kwargs, request=request)
        with patch.object(oauth,'refresh_tokens',side_effect=refresh):
            self.assertEqual(source.get(),'new')
            self.assertEqual(source.get(),'new')
            request.assert_called_once()
            self.assertEqual(store.load()['refreshToken'],'new-refresh')
            request.reset_mock();request.side_effect=oauth.OAuthError('fixed refresh failure')
            with self.assertRaises(oauth.OAuthError): source.get(force=True)
            request.assert_called_once()

    def test_proactive_refresh_new_session_and_cleanup(self):
        stop=threading.Event();api=Mock();api.tokens.expires_at=0
        api.session.return_value='https://socket.example'
        made=[]
        def factory():
            client=FakeSocket();made.append(client)
            if len(made)==2:
                api.tokens.expires_at=time.time()+3600
                stop.set()
            return client
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            r.run(api,self.intake,self.journal,self.token,stop=stop,factory=factory,tick=.001)
        self.assertEqual(api.session.call_count,2)
        self.assertTrue(all(s.closed for s in made))
        self.assertNotIn('secret',output.getvalue())


    def test_fatal_errors_are_not_overwritten_by_disconnect(self):
        s = r.Session(Mock(), self.intake, FakeSocket)
        s.accepting = True
        with patch.object(self.journal, 'add', side_effect=sqlite3.OperationalError('private-db')):
            s.donation(self.payload)
        fatal = s.failure
        s.disconnected()
        self.assertIs(s.failure, fatal)
        self.assertNotIsInstance(s.failure, r.TransientError)
        with self.assertRaises(r.ReceiverError): s.step()
        self.assertFalse(s.accepting)
        self.assertIsNone(self.journal.pending())
        s.close()

    def test_revoked_before_connected_processing_never_resubscribes(self):
        api = Mock(); sock = FakeSocket()
        s = r.Session(api, self.intake, lambda: sock)
        s.connect()
        s.system({'type':'revoked','data':{'eventType':'DONATION','channelId':'channel'}})
        s.disconnected()
        with self.assertRaises(r.ReceiverError) as error: s.step()
        self.assertNotIsInstance(error.exception, r.TransientError)
        api.subscribe.assert_not_called()
        s.donation(self.payload)
        self.assertIsNone(self.journal.pending())
        s.close()

    def test_storage_failure_during_subscribe_is_not_hidden(self):
        api = Mock(); s = r.Session(api, self.intake, FakeSocket)
        def subscribe(key):
            with patch.object(self.journal, 'add', side_effect=sqlite3.OperationalError('private-db')):
                s.donation(self.payload)
            s.disconnected()
            raise r.TransientError('fixed HTTP timeout')
        api.subscribe.side_effect = subscribe
        s.connect()
        with self.assertRaises(r.ReceiverError) as error: s.step()
        self.assertNotIsInstance(error.exception, r.TransientError)
        self.assertIsNone(self.journal.pending())
        s.close()

    def test_handshake_cannot_reclassify_storage_failure_as_transient(self):
        sock = FakeSocket(); s = r.Session(Mock(), self.intake, lambda: sock)
        def connect(*args, **kwargs):
            s.fail(r.ReceiverError('fixed fatal storage error'))
            raise OSError('private-url')
        sock.connect = connect
        with self.assertRaises(r.ReceiverError) as error: s.connect()
        self.assertNotIsInstance(error.exception, r.TransientError)
        s.close()

    def test_invalid_donation_stops_instead_of_silent_loss(self):
        s = r.Session(Mock(), self.intake, FakeSocket); s.accepting = True
        s.donation('private-invalid-json')
        with self.assertRaises(r.ReceiverError) as error: s.step()
        self.assertNotIn('private', str(error.exception))
        self.assertFalse(s.accepting)
        s.close()

    def test_unsolicited_confirmation_and_changed_key(self):
        s = r.Session(Mock(), self.intake, FakeSocket)
        s.system({'type':'subscribed','data':{'eventType':'DONATION','channelId':'channel'}})
        with self.assertRaises(r.ReceiverError): s.step()
        self.assertFalse(s.subscribed); s.close()
        s = r.Session(Mock(), self.intake, FakeSocket)
        s.connect(); s.step()
        s.system({'type':'connected','data':{'sessionKey':'different-key'}})
        with self.assertRaises(r.TransientError): s.step()
        s.close()

    def test_duplicate_mapping_key_is_rejected(self):
        p = Path(self.tmp.name)/'duplicate.json'
        p.write_text('{"1000":1000,"1000":30000}')
        with self.assertRaises(r.ReceiverError): r.amount_map(p)

    def test_engineio_dispatch_preserves_wire_order_without_worker_threads(self):
        try:
            from engineio import packet
            client = r.socket_client()
        except ImportError: self.skipTest('Install bridge/requirements.txt')
        received = []
        caller = threading.get_ident()
        client.eio.on('message', lambda value: received.append((value, threading.get_ident())))
        with patch.object(client.eio, 'start_background_task', side_effect=AssertionError('out-of-order worker')):
            for value in ('connected', 'donation-1', 'donation-2', 'revoked'):
                client.eio._receive_packet(packet.Packet(packet.MESSAGE, data=value))
        self.assertEqual(received, [(v, caller) for v in ('connected','donation-1','donation-2','revoked')])

    def test_local_bridge_token_never_follows_proxy_or_redirect(self):
        proxy_requests = []
        target_requests = []
        class Target(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): target_requests.append(self.path); self.send_response(200);self.end_headers()
            def do_POST(self): self.do_GET()
        target = HTTPServer(('127.0.0.1',0), Target)
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                if self.path.startswith('http:'): proxy_requests.append(self.path)
                self.send_response(302)
                self.send_header('Location','http://127.0.0.1:'+str(target.server_port)+'/stolen')
                self.end_headers()
        source = HTTPServer(('127.0.0.1',0), Redirect)
        for server in (target, source):
            thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with patch.dict(os.environ, {'http_proxy':'http://127.0.0.1:'+str(source.server_port),
                                      'HTTP_PROXY':'http://127.0.0.1:'+str(source.server_port),
                                      'no_proxy':'','NO_PROXY':''}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                r.bridge.deliver('bread','event-id','private-token',source.server_port)
            self.assertEqual(error.exception.code,302)
            error.exception.close()
        self.assertEqual(proxy_requests, [])
        self.assertEqual(target_requests, [])


@unittest.skipUnless(shutil.which('node') and (Path(__file__).parent/'socketio2/node_modules/socket.io').exists(),
                     'Optional local Socket.IO 2.0.3 fixture: npm ci --prefix tests/socketio2 --ignore-scripts')
class SocketIO2Integration(unittest.TestCase):
    def test_real_engineio3_disconnect_new_session_and_paper_retry(self):
        try: import socketio
        except ImportError: self.skipTest('Install bridge/requirements.txt')
        del socketio
        fixture=Path(__file__).parent/'socketio2/server.js'
        node=subprocess.Popen(['node',str(fixture)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(lambda: node.poll() is None and node.kill())
        port=int(node.stdout.readline().strip())
        class LocalApi(r.Api):
            ROOT='http://127.0.0.1:'+str(port)
        class Tokens:
            expires_at=time.time()+3600
            def get(self,force=False): return 'test-access'
        # Only TEST transport rewrites HTTPS to loopback HTTP. Production never does.
        def factory():
            client=r.socket_client();connect=client.connect
            client.connect=lambda url,**kw:connect(url.replace('https://127.0.0.1', 'http://127.0.0.1:'+str(port)),**kw)
            return client
        seen=set();requests=[];stop=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.assertions()
            def assertions(self):
                assert self.path=='/event'
                assert self.headers['X-EJT-Token']=='test-paper-token'
                event_id,effect=self.rfile.read(int(self.headers['Content-Length'])).decode().split('\t')
                assert effect=='bread'
                requests.append(event_id)
                if not seen:
                    seen.add(event_id)
                    self.close_connection=True  # Accepted, but acknowledgement lost.
                    return
                result='duplicate' if event_id in seen else 'queued'
                seen.add(event_id)
                self.send_response(200);self.end_headers();self.wfile.write(result.encode())
        paper=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=paper.serve_forever,daemon=True);thread.start()
        self.addCleanup(paper.server_close);self.addCleanup(paper.shutdown)
        with tempfile.TemporaryDirectory() as tmp:
            token=Path(tmp)/'token';token.write_text('test-paper-token')
            journal=r.Journal(Path(tmp)/'data/inbox.sqlite3')
            self.addCleanup(journal.close)
            intake=r.Intake(journal,'test-channel',{'1000':1000},allow_game_events=True)
            timer=threading.Timer(15,stop.set);timer.start()
            def watch():
                while not stop.wait(.02):
                    if journal.counts().get('done')==2: stop.set()
            watcher=threading.Thread(target=watch,daemon=True);watcher.start()
            out=io.StringIO()
            try:
                with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
                    r.run(LocalApi(Tokens()),intake,journal,token,paper.server_port,stop,factory,tick=.02,delivery_enabled=True)
            finally:
                stop.set();timer.cancel();watcher.join(2)
            self.assertEqual(journal.counts(),{'done':2},out.getvalue())
            self.assertEqual(len(seen),2)
            self.assertGreaterEqual(len(requests),3)
            self.assertEqual(requests[0],requests[1])
            for secret in ('test-access','test-paper-token','private-donor','private-name','private-text','auth='):
                self.assertNotIn(secret,out.getvalue())
        node.terminate();node.wait(3)
        stderr = node.stderr.read()
        # Node 24 emits a url.parse deprecation warning for legacy Socket.IO 2.
        # No server assertion failure or secret output is permitted.
        if stderr:
            self.assertIn('[DEP0169]', stderr)
        self.assertNotIn('AssertionError', stderr)
        for secret in ('private-', 'auth=', 'test-access', 'test-paper-token'):
            self.assertNotIn(secret, stderr)
        node.stdout.close();node.stderr.close()


if __name__=='__main__':unittest.main()
