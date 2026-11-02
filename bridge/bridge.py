"""EnJapToi local test bridge. Does NOT connect to CHZZK yet.
Python 3.10+ standard library only. This script simulates incoming donations.
"""
import argparse, base64, json, secrets, pathlib, unicodedata, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent
# Game cheese tiers only. Never infer these from the official KRW payAmount.
PRICE = {"buff":1000,"move":1000,"bread":1000,"pickaxe":1000,"debuff":2000,"surface":3000,"chancekill":4000,"clear":5000,"kill":30000}


def select_event(amount, message):
    """Messages are display/input data only; they never choose an effect."""
    if amount == 1000: return secrets.choice(["buff", "move", "bread", "pickaxe"])
    return {2000:"debuff", 3000:"surface", 4000:"chancekill", 5000:"clear", 30000:"kill"}.get(amount)


def safe_donor(value):
    """Display-only allowlist. Invalid/ambiguous input becomes anonymous, never rewritten into another name."""
    if not isinstance(value, str):
        return None
    value = value.strip(' ')
    if not 1 <= len(value) <= 32 or value.casefold() in ('익명', '익명의 후원자', 'anonymous'):
        return None
    categories = [unicodedata.category(ch) for ch in value]
    if not (categories[0].startswith('L') or categories[0] == 'Nd'):
        return None
    if any(not (cat.startswith('L') or cat == 'Nd' or cat.startswith('M') or ch in ' _-.')
           for ch, cat in zip(value, categories)):
        return None
    if len(value.encode('utf-8')) > 128:
        return None
    return value


class _NoLocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def deliver(event, event_id, token, port, instance=None, cheese=None, donor=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/event", data=f"{event_id}\t{event}".encode(),headers={"X-EJT-Token":token},method="POST")
    if instance is not None:
        req.add_header("X-EJT-Instance",instance)
    if cheese is not None:
        req.add_header("X-EJT-Cheese",str(cheese))
    donor = safe_donor(donor)
    if donor is not None and instance is not None and cheese == PRICE.get(event):
        req.add_header("X-EJT-Donor",base64.urlsafe_b64encode(donor.encode('utf-8')).decode('ascii').rstrip('='))
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
    if not event: print("No event: unsupported cheese tier");return
    token=pathlib.Path(args.token_file).read_text(encoding="utf-8").strip()
    event_id=args.id or secrets.token_urlsafe(18)
    print(json.dumps({"event":event,"id":event_id,"result":deliver(event,event_id,token,args.port)},ensure_ascii=False))

if __name__=="__main__": main()
