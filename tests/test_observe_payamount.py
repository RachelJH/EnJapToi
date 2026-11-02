import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch
from bridge import receiver


class ObservePayAmountTests(unittest.TestCase):
    def setUp(self):
        self.journal = Mock()
        self.journal.add.return_value = 'mock-receipt'
        self.payload = {
            'channelId': 'private-channel', 'donationType': 'CHAT',
            'payAmount': '1000', 'donationText': '!밥 private-message',
            'donatorNickname': 'private-nickname', 'donatorChannelId': 'private-donor',
            'token': 'private-token', 'clientSecret': 'private-secret',
        }

    def receive(self, payload, enabled=False, donation_type='CHAT'):
        intake = receiver.Intake(self.journal, 'private-channel', {'1000':1000},
                                 donation_type, allow_game_events=enabled)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = intake.receive(payload)
        self.assertEqual(err.getvalue(), '')
        return result, out.getvalue()

    def test_observation_logs_only_valid_amount_and_krw_without_selecting_effect(self):
        for amount in ('1000', '2000', '3000', '4000', '5000', '30000', '1234'):
            with self.subTest(amount=amount), patch.object(receiver.bridge, 'select_event', side_effect=AssertionError('observation must not select an effect')):
                result, output = self.receive(dict(self.payload, payAmount=amount))
            self.assertFalse(result)
            self.assertEqual(output, f'payAmount={amount} KRW\n')
            self.assertNotIn('private-', output)
        self.assertTrue(all(call.args == (None,) for call in self.journal.add.call_args_list))

    @patch.object(receiver.bridge.secrets,'choice',return_value='bread')
    def test_delivery_enabled_never_logs_amount_and_conversion_is_unchanged(self, choice):
        result, output = self.receive(self.payload, enabled=True)
        self.assertTrue(result)
        self.assertEqual(output, '')
        self.assertEqual(self.journal.add.call_args.args[0], 'bread')

    def test_wrong_channel_type_message_or_amount_is_not_logged(self):
        changes = [
            {'channelId':'another-channel'}, {'channelId':None}, {'donationType':'VIDEO'},
            {'donationType':'UNKNOWN'}, {'donationText':None}, {'donationText':'x'*16385},
        ]
        changes += [{'payAmount':value} for value in
                    (None, 1000, 1000.0, True, [], {}, '', '0', '-1000', '1,000',
                     '1000.0', '01000', ' 1000', '1000 ', '1000\nprivate-token',
                     '１０００', '١٠٠٠', '1'*13)]
        for change in changes:
            with self.subTest(field=next(iter(change))):
                result, output = self.receive(dict(self.payload, **change))
                self.assertFalse(result)
                self.assertEqual(output, '')

    def test_malformed_event_has_no_amount_or_private_output(self):
        intake = receiver.Intake(self.journal, 'private-channel', {})
        for value in ('private-invalid-json', [], None, 1000):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(receiver.ReceiverError):
                intake.receive(value)
            self.assertEqual(out.getvalue(), '')

    def test_json_event_and_selected_video_type_use_same_safe_log(self):
        result, output = self.receive(json.dumps(self.payload))
        self.assertFalse(result); self.assertEqual(output, 'payAmount=1000 KRW\n')
        result, output = self.receive(dict(self.payload, donationType='VIDEO'), donation_type='VIDEO')
        self.assertFalse(result); self.assertEqual(output, 'payAmount=1000 KRW\n')


if __name__ == '__main__':
    unittest.main()
