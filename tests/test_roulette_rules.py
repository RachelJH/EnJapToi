import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from bridge import bridge, receiver

class RouletteRulesTests(unittest.TestCase):
    def test_uniform_choice_candidates_for_all_commandless_tiers(self):
        for amount,candidates in ((1000,['buff','move','bread','pickaxe']),
                                  (2000,['mob','debuff']), (5000,['clear','chancekill','surface'])):
            for selected in candidates:
                with patch.object(bridge.secrets,'choice',return_value=selected) as choice:
                    self.assertEqual(bridge.select_event(amount,''),selected)
                    choice.assert_called_once_with(candidates)
        with patch.object(bridge.secrets,'choice',side_effect=AssertionError('no roulette')):
            self.assertEqual(bridge.select_event(30000,''),'kill')

    def test_exact_commands_override_random_and_wrong_prices_never_roll(self):
        with patch.object(bridge.secrets,'choice',side_effect=AssertionError('no roulette for command')):
            for command,effect in bridge.ALIASES.items():
                price=bridge.PRICE[effect]
                self.assertEqual(bridge.select_event(price,command),effect)
                for wrong in (1000,2000,5000):
                    if wrong!=price:self.assertIsNone(bridge.select_event(wrong,command))
            self.assertEqual(bridge.select_event(2000,'!몹 !디버프'),'mob')
            self.assertIsNone(bridge.select_event(2000,'!밥 !몹'))
            self.assertEqual(bridge.select_event(30000,'!밥'),'kill')

    def test_only_exact_whitespace_separated_commands_are_recognized(self):
        with patch.object(bridge.secrets,'choice',return_value='debuff') as choice:
            self.assertEqual(bridge.select_event(2000,'일반 메시지 !몹!'),'debuff')
            choice.assert_called_once_with(['mob','debuff'])
        with patch.object(bridge.secrets,'choice',side_effect=AssertionError('unsupported price')):
            self.assertIsNone(bridge.select_event(123,''))

    def test_each_tier_chooses_once_and_retries_same_id_effect_and_amount(self):
        for amount, selected in ((1000,'bread'),(2000,'mob'),(5000,'clear')):
            with tempfile.TemporaryDirectory() as d:
                token=Path(d)/'token';token.write_text('mock-token')
                send=Mock(side_effect=[OSError('lost acknowledgement'),'duplicate'])
                receipts=receiver.PaperReceipts(token,18765,'instance',Mock(alive=lambda:True),send)
                intake=receiver.Intake(receipts,'channel',{'123':amount},allow_game_events=True)
                with patch.object(bridge.secrets,'choice',return_value=selected) as choice:
                    self.assertTrue(intake.receive(dict(channelId='channel',donationType='CHAT',payAmount='123',donationText='')))
                choice.assert_called_once()
                first, second=send.call_args_list
                self.assertEqual(first,second)
                self.assertEqual(first.args[0],selected)
                self.assertEqual(first.kwargs['cheese'],amount)

if __name__=='__main__':unittest.main()
