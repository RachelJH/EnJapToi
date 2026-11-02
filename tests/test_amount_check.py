import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from bridge import amount_check as check


class AmountCheckTests(unittest.TestCase):
    def test_all_six_tiers_are_unmapped_without_an_explicit_candidate(self):
        for tier in check.TIERS:
            report = check.compare(str(tier), tier, {})
            self.assertEqual(report['comparison'], 'UNMAPPED')
            self.assertIsNone(report['candidateCheese'])
            self.assertFalse(report['authorizesGameDelivery'])
            self.assertIn('NOT_REAL_AMOUNT_VERIFICATION', report['purpose'])

    def test_exact_lookup_agrees_with_candidate_without_using_a_ratio(self):
        # Fictional numbers deliberately differ from every game tier.
        for index, tier in enumerate(check.TIERS, 1):
            report = check.compare(str(index), tier, {str(index): tier})
            self.assertEqual(report['comparison'], 'MATCH')
            self.assertEqual(report['payAmountKrw'], str(index))
            self.assertEqual(report['expectedCheese'], tier)
            self.assertFalse(report['authorizesGameDelivery'])

    def test_mismatch_does_not_rewrite_candidate(self):
        mapping = {'7': 2000}
        report = check.compare('7', 3000, mapping)
        self.assertEqual(report['comparison'], 'MISMATCH')
        self.assertEqual(report['candidateCheese'], 2000)
        self.assertEqual(mapping, {'7': 2000})

    def test_effects_are_described_without_selecting_roulette_or_authenticating(self):
        with patch.object(check.bridge, 'select_event', side_effect=AssertionError('no selection')), \
             patch.object(check.bridge, 'deliver', side_effect=AssertionError('no delivery')), \
             patch.object(check.receiver.oauth, 'credentials', side_effect=AssertionError('no credentials')), \
             patch.object(check.receiver, 'Journal', side_effect=AssertionError('no queue')):
            self.assertEqual(check.compare('7', 1000, {})['expectedEffects'], ['buff', 'move', 'bread', 'pickaxe'])
            self.assertEqual(check.compare('7', 3000, {})['expectedEffects'], ['surface'])
            self.assertEqual(check.compare('7', 4000, {})['expectedEffects'], ['chancekill'])

    def test_invalid_amounts_and_tiers_are_rejected(self):
        for value in (None, 1000, True, '', '0', '01', '-1', '1.0', '1,000', ' 7', '7\nsecret', '１', '1' * 13):
            with self.assertRaises(ValueError):
                check.compare(value, 1000, {})
        for tier in (True, '1000', 1000.0, None, 123):
            with self.assertRaises(ValueError):
                check.compare('7', tier, {})

    def test_invalid_candidate_entries_are_rejected_even_when_unrelated(self):
        for mapping in ([], {'7': True}, {'7': 123}, {'01': 1000}, {7: 1000}, {'7': 1000, 'bad': 2000}):
            with self.assertRaises(ValueError):
                check.compare('7', 1000, mapping)

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main(args)
        self.assertEqual(err.getvalue(), '')
        return code, out.getvalue()

    def test_cli_reads_candidate_only_and_reports_mismatch_with_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'candidate.json'
            path.write_text('{"7":2000}', encoding='utf-8-sig')
            before = path.read_bytes()
            code, output = self.invoke(['--pay-amount', '7', '--expected-cheese', '3000', '--amount-map', str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['comparison'], 'MISMATCH')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['candidate.json'])

    def test_cli_does_not_print_raw_bad_arguments_or_duplicate_key_map(self):
        for args in (['--private-token'], ['--pay-amount', 'private-token', '--expected-cheese', '1000'],
                     ['--pay-amount', '7', '--expected-cheese', 'private-token']):
            code, output = self.invoke(args)
            self.assertEqual(code, 1)
            self.assertNotIn('private-token', output)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private-map.json'
            path.write_text('{"7":1000,"7":2000}')
            code, output = self.invoke(['--pay-amount', '7', '--expected-cheese', '1000', '--amount-map', str(path)])
            self.assertEqual(code, 1)
            self.assertNotIn(str(path), output)

    def test_cli_without_map_never_treats_equal_digits_as_verified(self):
        code, output = self.invoke(['--pay-amount', '1000', '--expected-cheese', '1000'])
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report['comparison'], 'UNMAPPED')
        self.assertFalse(report['authorizesGameDelivery'])


if __name__ == '__main__':
    unittest.main()
