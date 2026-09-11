"""Place a single outbound test call for one scenario.

Usage:
    python -m src.place_call 08-closed-hours-edge-case
"""

import sys

from twilio.rest import Client

from scenarios.scenarios import SCENARIOS, get_scenario
from src.config import config

client = Client(config.twilio_account_sid, config.twilio_auth_token)


def place_call(scenario_id: str):
    scenario = get_scenario(scenario_id)
    print(f"Placing call — {scenario.id}: {scenario.label}")

    call = client.calls.create(
        to=config.pgai_test_number,
        from_=config.twilio_from_number,
        # Twilio fetches this once the line connects; server.py answers
        # with the <Stream> instruction that opens the audio bridge.
        url=f"{config.public_base_url}/twiml/{scenario.id}",
        method="POST",
        # Dual-channel recording puts each side of the call on its own
        # mono track. That makes speaker labeling in the transcript a
        # known fact rather than a guess from a diarization model.
        record=True,
        recording_channels="dual",
        # Cap enforced by Twilio itself, so it still applies if this
        # process dies mid-call.
        time_limit=config.max_call_duration_seconds,
        # Ring timeout only — how long to wait for pickup.
        timeout=30,
        # NOTE: no machine_detection. The pgai agent is an AI voice, so
        # Twilio's answering-machine detector classifies it as a machine
        # and, with DetectMessageEnd, waits for the "message" to finish
        # before running our TwiML — which never happens, so the stream
        # never starts and the bot is silent. We are deliberately calling
        # an automated agent, so we connect and stream immediately.
    )

    print(f"  call SID: {call.sid}")
    return call


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.place_call <scenario_id>\n")
        print("Available scenarios:")
        for scenario in SCENARIOS:
            print(f"  {scenario.id:<32} {scenario.label}")
        sys.exit(1)

    place_call(sys.argv[1])


if __name__ == "__main__":
    main()