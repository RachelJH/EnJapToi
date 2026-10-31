import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
from bridge.lifecycle import ParentLifetime
from bridge import receiver as r

class LifetimeTests(unittest.TestCase):
    def test_pipe_eof_stops_intake_and_acceptance(self):
        read,write=os.pipe();exited=threading.Event()
        stream=os.fdopen(read,'rb')
        guard=ParentLifetime(stream,terminate=lambda _:exited.set())
        self.assertTrue(guard.alive());os.close(write)
        self.assertTrue(exited.wait(2));self.assertFalse(guard.alive());stream.close()
        send=Mock();receipts=r.PaperReceipts('never-read',18765,'instance',guard,send)
        receipts.add('kill');send.assert_not_called()
        self.assertEqual(receipts.counts()['done'],0)

    def test_unknown_ack_uses_same_id_and_effect_without_disk_outbox(self):
        with tempfile.TemporaryDirectory() as d:
            token=Path(d)/'token';token.write_text('mock-token')
            send=Mock(side_effect=[OSError('mock-ack-lost'),'duplicate'])
            receipts=r.PaperReceipts(token,18765,'new-instance',Mock(alive=lambda:True),send)
            receipts.add('bread')
            first,second=send.call_args_list
            self.assertEqual(first.args,second.args)
            self.assertEqual(first.kwargs,{'instance':'new-instance'})
            self.assertEqual(receipts.counts()['done'],1)
            self.assertIsNone(receipts.pending())
            self.assertEqual([p.name for p in Path(d).iterdir()],['token'])

    def test_server_offline_donations_never_replay_on_restart(self):
        with tempfile.TemporaryDirectory() as d:
            token=Path(d)/'token';token.write_text('mock-token')
            send=Mock(side_effect=OSError('server-offline'))
            old=r.PaperReceipts(token,18765,'old',Mock(alive=lambda:True),send)
            intake=r.Intake(old,'channel',{'30000':30000},allow_game_events=True)
            intake.receive(dict(channelId='channel',donationType='CHAT',payAmount='30000',donationText=''))
            self.assertEqual(old.counts()['dropped'],1)
            new_send=Mock(return_value='queued')
            new=r.PaperReceipts(token,18765,'new',Mock(alive=lambda:True),new_send)
            self.assertIsNone(new.pending());new_send.assert_not_called()
            self.assertEqual(new.counts()['done'],0)

    def test_managed_observation_never_selects_or_delivers_effect(self):
        send=Mock(side_effect=AssertionError('amount safety must block delivery'))
        receipts=r.PaperReceipts('never-read',18765,'instance',Mock(alive=lambda:True),send)
        intake=r.Intake(receipts,'channel',{'30000':30000})
        with patch.object(r.bridge,'select_event',side_effect=AssertionError('must not select game effect')):
            self.assertFalse(intake.receive(dict(channelId='channel',donationType='CHAT',payAmount='30000',donationText='')))
        send.assert_not_called();self.assertEqual(receipts.counts()['ignored'],1)

    def test_actual_child_exits_on_parent_pipe_close_even_if_worker_is_blocked(self):
        code='from bridge.lifecycle import ParentLifetime;import sys,time;ParentLifetime(sys.stdin.buffer);print("ready",flush=True);time.sleep(60)'
        child=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready')
            child.stdin.close();self.assertEqual(child.wait(3),0)
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdout.close();child.stderr.close()

    def test_standalone_live_entry_refuses_before_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            mapping=Path(d)/'map';mapping.write_text('{}')
            args=['--channel-id','channel','--amount-map',str(mapping),'--token-file','unused']
            with patch.object(r.oauth,'credentials',side_effect=AssertionError('must not authenticate')),patch('sys.stdout',new_callable=io.StringIO):
                self.assertEqual(r.main(args),1)

    def test_os_lock_is_released_when_process_is_killed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'tokens.dat'
            code='from bridge.oauth import TokenStore;import sys,time\nwith TokenStore(sys.argv[1]).lock():\n print("ready",flush=True)\n time.sleep(60)'
            child=subprocess.Popen([sys.executable,'-c',code,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready');child.kill();child.wait(3)
                with r.oauth.TokenStore(path).lock():pass
            finally:
                if child.poll() is None:child.kill();child.wait()
                child.stdout.close();child.stderr.close()

if __name__=='__main__':unittest.main()
