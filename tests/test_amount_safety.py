import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from bridge import receiver as r
from bridge import donation_check as check

FIXTURES=Path(__file__).parent/'fixtures'

class AmountSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'private/inbox.sqlite3'
        self.journal=r.Journal(self.path);self.addCleanup(lambda:self.journal.close())
        self.mapping=r.amount_map(FIXTURES/'simulation-amount-map.json')
        self.payloads=json.loads((FIXTURES/'donations.json').read_text())
        self.proof=Path(self.tmp.name)/'verification.json'

    def write_proof(self,**changes):
        value=dict(version=1,confirmedByOperator=True,channelId='simulation-channel',mappingSha256=r.mapping_digest(self.mapping))
        value.update(changes);self.proof.write_text(json.dumps(value));return self.proof

    def test_official_message_shapes_all_rule_commands_simulation_only(self):
        with patch.object(r.bridge,'deliver',side_effect=AssertionError('network forbidden')), \
             patch.object(r.oauth,'credentials',side_effect=AssertionError('credentials forbidden')):
            result=check.check(self.payloads,self.mapping)
        self.assertEqual([x['effect'] for x in result['results']],
                         ['buff','move','bread','pickaxe','mob','debuff','clear','chancekill','surface','kill'])
        self.assertIn('SIMULATION_ONLY',result['validation'])
        self.assertNotIn('fictional-donor',json.dumps(result))
        self.assertNotIn('가상후원자',json.dumps(result,ensure_ascii=False))

    def test_string_krw_is_not_a_default_identity_conversion(self):
        payload=self.payloads[2]
        self.assertIsNone(check.check([payload],{})['results'][0]['effect'])
        self.assertIsNone(check.check([payload],{'100':1000})['results'][0]['effect'])
        self.assertEqual(check.check([dict(payload,payAmount='100')],{'100':1000})['results'][0]['effect'],'bread')
        for amount in (1000,1000.0,'1,000','1000.0','-1000','0','01000'):
            self.assertIsNone(check.check([dict(payload,payAmount=amount)],self.mapping)['results'][0]['effect'])

    def test_existing_command_priority_price_and_roulette_are_reused(self):
        p=self.payloads[0]
        examples=[('1000','!밥 !이동','bread'),('1000','!몹',None),
                  ('5000','!밥',None),('30000','!밥','kill')]
        for amount,text,expected in examples:
            self.assertEqual(check.check([dict(p,payAmount=amount,donationText=text)],self.mapping)['results'][0]['effect'],expected)
        with patch.object(r.bridge.secrets,'choice',return_value='buff') as choice:
            self.assertEqual(check.check([dict(p,donationText='')],self.mapping)['results'][0]['effect'],'buff')
            choice.assert_called_once_with(['buff','move','bread','pickaxe'])

    def test_default_intake_blocks_even_with_nonempty_mapping(self):
        intake=r.Intake(self.journal,'simulation-channel',self.mapping)
        with patch.object(r.bridge,'select_event',side_effect=AssertionError('no effect selection')):
            self.assertFalse(intake.receive(self.payloads[2]))
        self.assertEqual(self.journal.counts(),{'ignored':1})
        self.assertIsNone(self.journal.pending())

    def test_gate_requires_flag_operator_channel_and_exact_mapping(self):
        self.assertFalse(r.authorize_delivery(False,None,'simulation-channel',self.mapping))
        self.write_proof()
        self.assertTrue(r.authorize_delivery(True,self.proof,'simulation-channel',self.mapping))
        for enabled,file,channel,mapping in [(True,None,'simulation-channel',self.mapping),
            (False,self.proof,'simulation-channel',self.mapping),(True,self.proof,'wrong-channel',self.mapping),
            (True,self.proof,'simulation-channel',{'1000':2000}),(True,self.proof,'simulation-channel',{})]:
            with self.assertRaises(r.ReceiverError):r.authorize_delivery(enabled,file,channel,mapping)
        for changed in ({'confirmedByOperator':False},{'confirmedByOperator':'true'},{'version':True},{'mappingSha256':'old'}):
            self.write_proof(**changed)
            with self.assertRaises(r.ReceiverError):r.authorize_delivery(True,self.proof,'simulation-channel',self.mapping)

    def test_observation_blocks_old_pending_and_never_reads_paper_token(self):
        self.journal.add('kill') # old, unverified row
        stop=threading.Event();api=Mock();api.tokens.expires_at=time.time()+3600
        def verify(channel):stop.set()
        api.verify_channel.side_effect=verify
        intake=r.Intake(self.journal,'simulation-channel',self.mapping,allow_game_events=True)
        class Socket:
            def on(self,*args):pass
            def connect(self,*args,**kwargs):pass
            def disconnect(self):pass
        with patch.object(r,'deliver_one',side_effect=AssertionError('observation must not deliver')), \
             contextlib.redirect_stdout(io.StringIO()):
            r.run(api,intake,self.journal,Path(self.tmp.name)/'nonexistent-token',stop=stop,factory=Socket,tick=.001)
        self.assertFalse(intake.allow_game_events)
        self.assertEqual(self.journal.counts(),{'pending':1})

    def test_restart_preserves_hash_and_holds_unverified_or_different_mapping(self):
        legacy_id=self.journal.add('kill')
        old_hash=r.mapping_digest({'1000':30000})
        self.journal.add('kill',old_hash)
        intake=r.Intake(self.journal,'simulation-channel',self.mapping,allow_game_events=True)
        intake.receive(self.payloads[2]);approved=r.mapping_digest(self.mapping)
        before=self.journal.pending(approved)
        self.journal.close();self.journal=r.Journal(self.path)
        send=Mock(return_value='queued');token=Path(self.tmp.name)/'token';token.write_text('mock-token')
        self.assertEqual(r.deliver_one(self.journal,token,send=send,mapping_hash=approved),'queued')
        self.assertEqual(send.call_args.args[:2],('bread',before[0]))
        self.assertEqual(self.journal.pending()[0],legacy_id)
        self.assertEqual(self.journal.counts(),{'pending':2,'done':1})
        self.assertEqual(self.journal.held_count(approved),2)

    def test_existing_database_is_migrated_without_approving_old_rows(self):
        path=Path(self.tmp.name)/'legacy.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE events(id TEXT PRIMARY KEY,effect TEXT,status TEXT,attempts INTEGER DEFAULT 0,retry_at REAL DEFAULT 0)')
            db.execute("INSERT INTO events(id,effect,status) VALUES('legacy-id','kill','pending')")
        journal=r.Journal(path)
        try:
            self.assertEqual(journal.pending()[0],'legacy-id')
            self.assertIsNone(journal.pending(r.mapping_digest(self.mapping)))
            self.assertEqual(journal.held_count(r.mapping_digest(self.mapping)),1)
        finally: journal.close()

    def test_windows_utf8_bom_config_is_supported(self):
        mapping_file=Path(self.tmp.name)/'map.json'
        mapping_file.write_text(json.dumps(self.mapping),encoding='utf-8-sig')
        self.assertEqual(r.amount_map(mapping_file),self.mapping)
        self.write_proof()
        self.proof.write_text(self.proof.read_text(),encoding='utf-8-sig')
        self.assertTrue(r.authorize_delivery(True,self.proof,'simulation-channel',self.mapping))

    def test_cli_defaults_fail_closed_before_any_credentials_when_enabling_unverified(self):
        args=['--channel-id','simulation-channel','--amount-map',str(FIXTURES/'simulation-amount-map.json'),
              '--token-file','never-read','--enable-game-delivery']
        with patch.object(r.oauth,'credentials',side_effect=AssertionError('must reject first')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(r.main(args),1)

    def test_offline_cli_does_not_create_operator_proof(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(check.main(['--input',str(FIXTURES/'donations.json'),'--amount-map',str(FIXTURES/'simulation-amount-map.json')]),0)
        result=json.loads(output.getvalue())
        self.assertIn('SIMULATION_ONLY',result['validation'])
        self.assertNotIn('confirmedByOperator',result)

if __name__=='__main__':unittest.main()
