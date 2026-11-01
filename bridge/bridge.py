"""EnJapToi local test bridge. Does NOT connect to CHZZK yet.
Python 3.10+ standard library only. This script simulates incoming donations.
"""
import argparse, json, secrets, pathlib, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent
ALIASES = {"!버프":"buff", "!이동":"move", "!밥":"bread", "!다곡":"pickaxe", "!몹":"mob", "!디버프":"debuff", "!삭제":"clear", "!랜덤즉사":"chancekill", "!지상":"surface", "!즉사":"kill"}
PRICE = {"buff":1000,"move":1000,"bread":1000,"pickaxe":1000,"mob":2000,"debuff":2000,"clear":5000,"chancekill":5000,"surface":5000,"kill":30000}

def select_event(amount, message):
    if amount == 30000: return "kill"
    words = message.split()
    matches = [ALIASES[w] for w in words if w in ALIASES]
    if matches:
        event = matches[0]
        return event if PRICE[event] == amount else None
    if amount == 1000: return secrets.choice(["buff", "move", "bread", "pickaxe"])
    return None

class _NoLocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def deliver(event, event_id, token, port, instance=None, cheese=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/event", data=f"{event_id}\t{event}".encode(),headers={"X-EJT-Token":token},method="POST")
    if instance is not None:
        req.add_header("X-EJT-Instance",instance)
    if cheese is not None:
        req.add_header("X-EJT-Cheese",str(cheese))
    # This credential is for loopback Paper only, never a proxy or redirect target.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoLocalRedirect())
    with opener.open(req,timeout=10) as resp:
        body = resp.read(129)
        if len(body) > 128:
            raise ValueError('Unexpected Paper response size')
        return body.decode()

def main():
    ap=argparse.ArgumentParser(description="Local simulation of donation -> Paper")
    ap.add_argument("--amount",type=int,required=True,help="Donation amount")
    ap.add_argument("--message",default="",help="Donation message")
    ap.add_argument("--id",default=None,help="Unique ID, for duplicate test")
    ap.add_argument("--token-file",required=True,help="Paper plugins/EnJapToi/bridge-token.txt")
    ap.add_argument("--port",type=int,default=18765)
    args=ap.parse_args()
    event=select_event(args.amount,args.message)
    if not event: print("No event: invalid/missing command for this amount");return
    token=pathlib.Path(args.token_file).read_text(encoding="utf-8").strip()
    event_id=args.id or secrets.token_urlsafe(18)
    print(json.dumps({"event":event,"id":event_id,"result":deliver(event,event_id,token,args.port)},ensure_ascii=False))

if __name__=="__main__": main()
