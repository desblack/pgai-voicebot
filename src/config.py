"""Configuration loading and validation.
 
Every other module imports from here rather than reading os.environ
directly, so a missing or wrong value fails loudly at startup instead of
silently mid-call. Mid-call failures are the expensive kind: you have
already dialed, and you are paying by the minute.
"""
 
import os
import re
import sys
 
from dotenv import load_dotenv
 
load_dotenv()
 
# The number the assessment tells us to call. Hard-coded on purpose, not
# just read from .env: the cost of getting this one value wrong (an
# automated dialer pointed at an unintended number) is wildly
# disproportionate to the cost of the check.
ASSESSMENT_NUMBER = "+18054398008"
 
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
 
 
def _required(name: str) -> str:
    """Read an environment variable or exit with a clear message."""
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example to .env and fill it in."
        )
    return value
 
 
class Config:
    def __init__(self) -> None:
        self.twilio_account_sid = _required("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = _required("TWILIO_AUTH_TOKEN")
        self.twilio_from_number = _required("TWILIO_FROM_NUMBER")
        self.pgai_test_number = _required("PGAI_TEST_NUMBER")
        self.openai_api_key = _required("OPENAI_API_KEY")
 
        # ngrok (or equivalent) HTTPS URL. Trailing slash stripped so
        # callers can safely concatenate paths.
        self.public_base_url = _required("PUBLIC_BASE_URL").rstrip("/")
 
        self.max_calls_per_run = int(os.environ.get("MAX_CALLS_PER_RUN", "15"))
        self.max_call_duration_seconds = int(
            os.environ.get("MAX_CALL_DURATION_SECONDS", "240")
        )
 
        self.openai_realtime_model = os.environ.get(
            "OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"
        )
 
        self._validate()
 
    def _validate(self) -> None:
        # Guardrail 1: refuse to dial anything but the assessment line.
        if self.pgai_test_number != ASSESSMENT_NUMBER:
            sys.exit(
                f"PGAI_TEST_NUMBER is {self.pgai_test_number}, but the assessment "
                f"specifies {ASSESSMENT_NUMBER}. Refusing to start.\n"
                f"If this is deliberate (e.g. a sandbox), edit ASSESSMENT_NUMBER in "
                f"src/config.py explicitly rather than just changing .env."
            )
 
        # Guardrail 2: the submission form requires ONE caller ID across
        # every test call, in E.164. Catching a malformed number here is
        # cheaper than discovering after 12 calls that the graders cannot
        # match your recordings to your submission.
        if not E164_PATTERN.match(self.twilio_from_number):
            sys.exit(
                f"TWILIO_FROM_NUMBER ({self.twilio_from_number}) is not valid E.164.\n"
                f"Expected form: +13175551234 (leading +, country code, no spaces "
                f"or dashes). This exact string goes on the submission form."
            )
 
        # Guardrail 3: Twilio reaches us over the public internet and
        # Media Streams require TLS, so an http:// tunnel silently fails.
        if not self.public_base_url.startswith("https://"):
            sys.exit(
                f"PUBLIC_BASE_URL must start with https:// (got "
                f"{self.public_base_url}). Twilio Media Streams require a secure "
                f"WebSocket, which means the tunnel must be HTTPS."
            )
 
    @property
    def websocket_base_url(self) -> str:
        """https://... -> wss://... for the Media Stream URL in TwiML."""
        return "wss://" + self.public_base_url[len("https://") :]
 
 
config = Config()
 
