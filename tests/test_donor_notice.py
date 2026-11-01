import base64
import contextlib
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from bridge import bridge, receiver


class DonorNoticeTests(unittest.TestCase):
    def payload(self, **changes):
        return dict(dict(channelId='channel', donationType='CHAT', payAmount='123',
                         donationText='!이동', donatorChannelId='private-donor-id',
                         donatorNickname='홍길동'), **changes)

    def test_allowlist_is_display_only_and_bounded(self):
        for name in ('홍길동', 'Donor_123', '김 후원자', 'Cafe\u0301', 'A' * 32):
            self.assertEqual(bridge.safe_donor(name), name)
        for name in (None, 123, {}, '', ' ', '익명', '익명의 후원자', 'Anonymous',
                     'A' * 33, '§a홍길동', '&a홍길동', '홍\n길동', '홍\r길동',
                     '홍\t길동', '홍\u202e길동', '홍\u200b길동', '홍\u2028길동',
                     '<click:run_command:/op>', '홍"길동', '/op admin', '홍\\길동', '\ud800'):
            self.assertIsNone(bridge.safe_donor(name))

    def test_normal_name_uses_verified_game_tier_and_same_metadata_on_retry(self):
        with tempfile.TemporaryDirectory() as d:
            token = Path(d) / 'token'; token.write_text('mock-token')
            send = Mock(side_effect=[OSError('not printed'), 'duplicate'])
            receipts = receiver.PaperReceipts(token, 18765, 'instance', Mock(alive=lambda:True), send)
            intake = receiver.Intake(receipts, 'channel', {'123':1000}, allow_game_events=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), patch.object(bridge, 'select_event', wraps=bridge.select_event) as select:
                self.assertTrue(intake.receive(self.payload()))
            self.assertEqual(out.getvalue(), '')
            select.assert_called_once_with(1000, '!이동')
            a, b = send.call_args_list
            self.assertEqual(a, b)
            self.assertEqual(a.args[0], 'move')
            self.assertEqual(a.kwargs, {'instance':'instance', 'cheese':1000, 'donor':'홍길동'})
            self.assertNotIn('private-donor-id', repr(a))
            self.assertNotIn('123', repr(a.kwargs))

    def test_missing_or_unsafe_name_or_identity_falls_back_without_lookups(self):
        for changes in ({'donatorNickname':None}, {'donatorNickname':''}, {'donatorNickname':'익명'},
                        {'donatorNickname':'&c관리자'}, {'donatorChannelId':None},
                        {'donatorChannelId':''}, {'donatorChannelId':'anonymous'}):
            journal = Mock()
            intake = receiver.Intake(journal, 'channel', {'123':1000}, allow_game_events=True)
            self.assertTrue(intake.receive(self.payload(**changes)))
            self.assertIsNone(journal.add.call_args.kwargs['donor'])
        # No network/user-lookup component is needed for nickname extraction.

    def test_observation_and_invalid_events_never_forward_or_log_name(self):
        journal = Mock()
        intake = receiver.Intake(journal, 'channel', {'123':1000})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(intake.receive(self.payload()))
            self.assertFalse(intake.receive(self.payload(payAmount='private-invalid')))
            self.assertFalse(intake.receive(self.payload(channelId='other')))
        self.assertEqual(out.getvalue(), 'payAmount=123 KRW\n')
        self.assertTrue(all(c.args == (None,) and not c.kwargs for c in journal.add.call_args_list))

    def test_legacy_mock_outbox_does_not_persist_identity(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'inbox.db'
            with contextlib.closing(receiver.Journal(path)) as journal:
                intake = receiver.Intake(journal, 'channel', {'123':1000}, allow_game_events=True)
                self.assertTrue(intake.receive(self.payload()))
            self.assertNotIn('홍길동'.encode(), path.read_bytes())
            self.assertNotIn(b'private-donor-id', path.read_bytes())

    def test_unicode_wire_header_is_bounded_encoded_and_legacy_send_stays_anonymous(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((dict(self.headers), self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.end_headers(); self.wfile.write(b'queued')
            def log_message(self, *args): pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            port = server.server_address[1]
            bridge.deliver('move', 'id1', 'mock-token', port, instance='instance', cheese=1000, donor='홍길동')
            bridge.deliver('move', 'id2', 'mock-token', port, donor='홍길동')
            bridge.deliver('move', 'id3', 'mock-token', port, instance='instance', cheese=1000, donor='홍\r\nInjected')
            headers, body = received[0]
            encoded = headers['X-Ejt-Donor']
            self.assertTrue(encoded.isascii()); self.assertLessEqual(len(encoded), 172)
            self.assertEqual(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode(), '홍길동')
            self.assertEqual(body, b'id1\tmove')
            self.assertNotIn('X-Ejt-Donor', received[1][0])
            self.assertNotIn('X-Ejt-Donor', received[2][0])
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
