import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from bridge import amount_mapping, receiver


class AmountMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'amount-map.json'

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding='utf-8')

    def payload(self, amount):
        return dict(channelId='channel', donationType='CHAT', payAmount=amount, donationText='')

    def test_empty_example_and_all_six_explicit_tiers(self):
        self.assertEqual(amount_mapping.load(Path(__file__).parents[1] / 'bridge/amount-map.example.json'), {})
        mapping = {str(71 + i): tier for i, tier in enumerate(sorted(amount_mapping.TIERS))}
        self.write(mapping)
        self.assertEqual(receiver.amount_map(self.path), mapping)
        self.assertNotIn('1000', mapping)  # No implicit 1:1 mapping.
        self.write({'71': 1000, '72': 1000})
        self.assertEqual(receiver.amount_map(self.path), {'71': 1000, '72': 1000})

    def test_missing_directory_empty_file_and_malformed_input_fail_closed(self):
        paths = [self.path, Path(self.temp.name)]
        for path in paths:
            with self.assertRaises(amount_mapping.MappingError):
                amount_mapping.load(path)
        for raw in ('', '{', 'null', '[]', '"secret-content"', '{"7":NaN}', '{"7":Infinity}'):
            self.path.write_text(raw)
            with self.assertRaises(receiver.ReceiverError) as error:
                receiver.amount_map(self.path)
            self.assertNotIn(str(self.path), str(error.exception))
            self.assertNotIn('secret-content', str(error.exception))

    def test_duplicate_keys_rejected_even_if_values_are_identical(self):
        for raw in ('{"7":1000,"7":1000}', '{"7":1000,"7":2000}', '{"7":1000,"\\u0037":2000}'):
            self.path.write_text(raw)
            with self.assertRaises(receiver.ReceiverError):
                receiver.amount_map(self.path)

    def test_invalid_keys_and_values_are_rejected(self):
        for key in ('0', '01', '-1', '1.0', '1,000', ' 7', '7\n', '１', '1' * 13):
            self.write({key: 1000})
            with self.assertRaises(receiver.ReceiverError):
                receiver.amount_map(self.path)
        for value in (True, False, None, '1000', 1000.0, 0, -1, 999, {}, []):
            self.write({'7': value})
            with self.assertRaises(receiver.ReceiverError):
                receiver.amount_map(self.path)

    def test_bom_supported_but_invalid_encoding_oversize_and_deep_nesting_rejected(self):
        self.path.write_text('{"7":1000}', encoding='utf-8-sig')
        self.assertEqual(receiver.amount_map(self.path), {'7': 1000})
        for raw in (b'\xff\xfe', b' ' * (amount_mapping.MAX_BYTES + 1), b'[' * 2000 + b']' * 2000):
            self.path.write_bytes(raw)
            with self.assertRaises(receiver.ReceiverError):
                receiver.amount_map(self.path)

    def test_unknown_amount_never_selects_or_enqueues_effect_even_with_delivery_enabled(self):
        self.write({'71': 1000})
        journal = Mock()
        intake = receiver.Intake(journal, 'channel', receiver.amount_map(self.path), allow_game_events=True)
        with patch.object(receiver.bridge, 'select_event', side_effect=AssertionError('unmapped amount selected')):
            self.assertFalse(intake.receive(self.payload('1000')))
        self.assertIsNone(journal.add.call_args.args[0])

    def test_file_edit_applies_only_to_next_startup_and_preserves_existing_queue(self):
        self.write({'71': 1000})
        old_mapping = receiver.amount_map(self.path)
        journal = receiver.Journal(Path(self.temp.name) / 'inbox.db')
        try:
            old = receiver.Intake(journal, 'channel', old_mapping, allow_game_events=True)
            with patch.object(receiver.bridge.secrets, 'choice', return_value='bread'):
                self.assertTrue(old.receive(self.payload('71')))
                before = journal.db.execute('SELECT id,effect,mapping_hash FROM events').fetchall()
                self.write({'72': 3000})
                self.assertTrue(old.receive(self.payload('71')))  # Running snapshot stays stable.
            new_mapping = receiver.amount_map(self.path)
            new = receiver.Intake(journal, 'channel', new_mapping, allow_game_events=True)
            self.assertFalse(new.receive(self.payload('71')))
            self.assertTrue(new.receive(self.payload('72')))
            rows = journal.db.execute("SELECT id,effect,mapping_hash FROM events WHERE status='pending' ORDER BY rowid").fetchall()
            self.assertEqual(rows[0], before[0])
            self.assertEqual([row[1] for row in rows], ['bread', 'bread', 'surface'])
            self.assertEqual(rows[-1][2], receiver.mapping_digest(new_mapping))
            self.assertEqual(journal.pending()[:2], before[0][:2])
            proof = Path(self.temp.name) / 'proof.json'
            proof.write_text(json.dumps(dict(version=1, confirmedByOperator=True, channelId='channel',
                                            mappingSha256=receiver.mapping_digest(old_mapping))))
            with self.assertRaises(receiver.ReceiverError):
                receiver.authorize_delivery(True, proof, 'channel', new_mapping)
            self.assertFalse(receiver.authorize_delivery(False, None, 'channel', new_mapping))
        finally:
            journal.close()

    def test_candidate_file_does_not_enable_observation_receiver(self):
        self.write({'71': 30000})
        journal = Mock()
        intake = receiver.Intake(journal, 'channel', receiver.amount_map(self.path))
        with patch.object(receiver.bridge, 'select_event', side_effect=AssertionError('delivery must remain disabled')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(intake.receive(self.payload('71')))
        self.assertIsNone(journal.add.call_args.args[0])

    def test_missing_operational_file_stops_startup_before_credentials_or_paper_receipts(self):
        with patch.dict(os.environ, {'EJT_SERVER_INSTANCE': 'test-instance'}), \
             patch.object(receiver.sys, 'stdin', SimpleNamespace(isatty=lambda: False, buffer=io.BytesIO())), \
             patch('bridge.lifecycle.ParentLifetime', return_value=Mock()), \
             patch.object(receiver.oauth, 'credentials', side_effect=AssertionError('no OAuth on bad map')), \
             patch.object(receiver, 'PaperReceipts', side_effect=AssertionError('no Paper on bad map')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(receiver.main(['--managed-stdin', '--channel-id', 'channel',
                                           '--amount-map', str(self.path), '--token-file', 'never-read']), 1)


if __name__ == '__main__':
    unittest.main()
