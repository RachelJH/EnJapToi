import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from bridge import bridge, receiver

class RouletteRulesTests(unittest.TestCase):
    def test_thousand_uses_exactly_four_equal_choice_candidates(self):
        candidates = ['buff', 'move', 'bread', 'pickaxe']
        for selected in candidates:
            with patch.object(bridge.secrets, 'choice', return_value=selected) as choice:
                self.assertEqual(bridge.select_event(1000, '!몹 !밥'), selected)
                choice.assert_called_once_with(candidates)

    def test_all_other_tiers_ignore_every_message_without_roulette(self):
        with patch.object(bridge.secrets, 'choice', side_effect=AssertionError('no roulette')):
            for amount, effect in ((2000,'debuff'),(3000,'surface'),(4000,'chancekill'),(5000,'clear'),(30000,'kill')):
                for message in ('', '!몹', '!밥 !이동', '!지상', '!랜덤즉사', '일반 메시지'):
                    self.assertEqual(bridge.select_event(amount, message), effect)
            for amount in (0,123,1001,None):
                self.assertIsNone(bridge.select_event(amount, '!즉사'))
        self.assertNotIn('mob', bridge.PRICE)

    def test_retries_keep_same_id_effect_and_tier(self):
        for amount, selected in ((1000,'bread'),(2000,'debuff'),(3000,'surface'),(4000,'chancekill'),(5000,'clear'),(30000,'kill')):
            with tempfile.TemporaryDirectory() as d:
                token=Path(d)/'token';token.write_text('mock-token')
                send=Mock(side_effect=[OSError('lost acknowledgement'),'duplicate'])
                receipts=receiver.PaperReceipts(token,18765,'instance',Mock(alive=lambda:True),send)
                intake=receiver.Intake(receipts,'channel',{'123':amount},allow_game_events=True)
                with patch.object(bridge.secrets,'choice',return_value=selected) as choice:
                    self.assertTrue(intake.receive(dict(channelId='channel',donationType='CHAT',payAmount='123',donationText='!몹')))
                self.assertEqual(choice.call_count, 1 if amount==1000 else 0)
                first, second=send.call_args_list
                self.assertEqual(first,second)
                self.assertEqual(first.args[0],selected)
                self.assertEqual(first.kwargs['cheese'],amount)

    def test_legacy_mob_is_retired_without_token_delivery_reroll_or_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'inbox.db'
            journal=receiver.Journal(path)
            event_id=journal.add('mob')
            next_id=journal.add('bread')
            journal.close()
            journal=receiver.Journal(path)
            try:
                with patch.object(bridge.secrets,'choice',side_effect=AssertionError('no reroll')):
                    send=Mock(side_effect=AssertionError('no mob delivery'))
                    self.assertEqual(receiver.deliver_one(journal,Path(d)/'missing-token',send=send),'retired')
                    send.assert_not_called()
                self.assertEqual(journal.db.execute('SELECT effect,status FROM events WHERE id=?',(event_id,)).fetchone(),('mob','retired'))
                self.assertEqual(journal.pending()[:2],(next_id,'bread'))
            finally: journal.close()

if __name__=='__main__':unittest.main()
