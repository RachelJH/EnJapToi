"""Paper lifecycle integration fixture: fake CHZZK, real local Paper HTTP.
Never logs in. Invoked by the TEST server instead of receiver.py.
"""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from bridge import receiver as r

class Socket:
    def __init__(self):self.handlers={}
    def on(self,name,handler):self.handlers[name]=handler
    def connect(self,*args,**kwargs):
        self.handlers['SYSTEM']({'type':'connected','data':{'sessionKey':'fixture-key'}})
    def disconnect(self):pass

sock=Socket()
class Api:
    def __init__(self,tokens):self.tokens=tokens;tokens.expires_at=time.time()+3600
    def verify_channel(self,channel):assert channel=='fixture-channel'
    def session(self):return 'https://fixture.invalid'
    def subscribe(self,key):
        sock.handlers['SYSTEM']({'type':'subscribed','data':{'eventType':'DONATION','channelId':'fixture-channel'}})
        sock.handlers['DONATION']({'donationType':'CHAT','channelId':'fixture-channel','payAmount':'1000','donationText':'!밥'})

real_run=r.run
def run(*args,**kwargs):
    Path('receiver-fixture.pid').write_text(str(os.getpid()))
    kwargs['factory']=lambda:sock
    return real_run(*args,**kwargs)
r.run=run
r.Api=Api
r.oauth.credentials=lambda config:('fixture-client','fixture-secret')
raise SystemExit(r.main())
