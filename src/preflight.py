""" Verifgy everything works before placing a single billable call.
Run this after filling in .env and starting ngrok:
    python -m src.prefligh

Every chech here is cheap. Discovering a bad key or an unrachable tunnel now cost nothing: discovering it after dialing costs money
and produces a useless recording"""

import shutil
import subprocess
import sys

import requests 
from openai import OpenAI
from twilio.rest import Client 

from scenarios.scenarios import SCENARIOS
from src.config import config 

PASS = " PASS"
FAIL = " FAIL"

def check_ffmpeg() -> bool:
    if shutil.which("ffmpeg") is None:
        print(f"{FAIL} ffmpeg not on PATH - transcription will fail")
        print("         install: brew install ffmpeg")
        return False 
    version = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True
    ).stdout.splitlines()[0]
    print(f"{PASS} ffmpeg - {version[:50]}")
    return True 
def check_twilio() -> bool:
    try:
        client = Client(config.twilio_account_sid, config.twilio_auth_token)
        account = client.api.v2010.accounts(config.twilio_account_sid).fetch()
        print(f"{PASS} Twilio auth — {account.friendly_name} ({account.status})")
 
        if account.type == "Trial":
            print("       WARNING: trial account. Trial accounts can only dial")
            print("       pre-verified numbers, so calls to the test line will")
            print("       fail. Upgrade before running the suite.")
 
        numbers = client.incoming_phone_numbers.list()
        owned = [n.phone_number for n in numbers]
        if config.twilio_from_number in owned:
            print(f"{PASS} Caller ID {config.twilio_from_number} is owned by account")
        else:
            print(f"{FAIL} {config.twilio_from_number} not found in this account")
            print(f"       numbers on account: {owned or 'none'}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} Twilio — {exc}")
        return False



def check_openai() -> bool:
    try:
        client = OpenAI(api_key=config.openai_api_key)
        models = client.models.list()
        names = {m.id for m in models.data}
        print(f"{PASS} OpenAI auth — {len(names)} models visible")
 
        if config.openai_realtime_model in names:
            print(f"{PASS} Realtime model '{config.openai_realtime_model}' available")
        else:
            realtime = sorted(n for n in names if "realtime" in n)
            print(
                f"{FAIL} '{config.openai_realtime_model}' not visible to this key"
            )
            print(f"       realtime models you can see: {realtime or 'none'}")
            print("       set OPENAI_REALTIME_MODEL in .env to one of these")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} OpenAI — {exc}")
        return False
 
 
def check_tunnel() -> bool:
    """Confirm the public URL actually reaches this machine.
 
    Twilio has to fetch TwiML from here over the internet. If the tunnel
    is down or PUBLIC_BASE_URL is stale, calls connect and then fail with
    Twilio error 31902, which is confusing to diagnose from the call log.
    """
    url = f"{config.public_base_url}/health"
    try:
        response = requests.get(url, timeout=10)
        if response.ok and response.json().get("status") == "ok":
            print(f"{PASS} Tunnel reachable — {url}")
            return True
        print(f"{FAIL} Tunnel returned {response.status_code} from {url}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} Tunnel unreachable at {url}")
        print(f"       {exc}")
        print("       Is the server running (python -m src.server)?")
        print("       Is ngrok running, and does PUBLIC_BASE_URL match it?")
        return False
 
 
def main() -> None:
    print("Preflight checks\n")
    print(f"  caller ID:  {config.twilio_from_number}")
    print(f"  dialing:    {config.pgai_test_number}")
    print(f"  scenarios:  {len(SCENARIOS)}")
    print(f"  caps:       {config.max_calls_per_run} calls, "
          f"{config.max_call_duration_seconds}s each\n")
 
    results = [
        check_ffmpeg(),
        check_twilio(),
        check_openai(),
        check_tunnel(),
    ]
 
    print()
    if all(results):
        est = len(SCENARIOS) * 1.0
        print(f"All checks passed. Estimated suite cost: ~${est:.0f}")
        print("Start with one call before the full suite:")
        print("  python -m src.place_call 01-simple-schedule")
    else:
        print("Fix the failures above before placing calls.")
        sys.exit(1)
 
 
if __name__ == "__main__":
    main()