"""Download recordings, split channels, transcribe, and merge.

The recording Twilio produces is dual-channel: channel 0 is one side of
the call, channel 1 the other. Splitting it with ffmpeg and transcribing
each mono file separately means speaker labels come from which file the
text came from — a known fact — instead of asking a diarization model to
infer who was speaking from a mixed signal.

Usage:
    python -m src.transcribe --all          # everything in call_log.json
    python -m src.transcribe CAxxxxxxxx     # one call
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import requests
from openai import OpenAI
from twilio.rest import Client

from src.config import config

twilio_client = Client(config.twilio_account_sid, config.twilio_auth_token)
openai_client = OpenAI(api_key=config.openai_api_key)

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS_DIR = ROOT / "recordings"
TRANSCRIPTS_DIR = ROOT / "transcripts"
CALL_LOG = ROOT / "call_log.json"


def download_recording(call_sid: str, retries: int = 3) -> Path:
    """Fetch the call's MP3. Retries because recordings finalize slightly
    after the call ends, so an immediate fetch can 404."""
    RECORDINGS_DIR.mkdir(exist_ok=True)

    recordings = []
    for attempt in range(retries):
        recordings = twilio_client.recordings.list(call_sid=call_sid, limit=1)
        if recordings:
            break
        if attempt < retries - 1:
            print(f"  recording not ready, retrying in 10s...")
            time.sleep(10)

    if not recordings:
        raise RuntimeError(f"No recording found for call {call_sid}")

    recording = recordings[0]
    # MP3 satisfies the brief's "OGG or MP3" requirement for submitted audio.
    url = f"https://api.twilio.com{recording.uri.replace('.json', '.mp3')}"

    # The recording can appear in the list (metadata) before the MP3
    # itself is finalized and downloadable — so the download needs its
    # own retry, separate from the metadata lookup above. Without this,
    # a call whose audio is still encoding fails with a 404 and its
    # transcript is lost.
    response = None
    for attempt in range(5):
        response = requests.get(
            url, auth=(config.twilio_account_sid, config.twilio_auth_token), timeout=60
        )
        if response.status_code == 200:
            break
        if attempt < 4:
            print(f"  MP3 not finalized yet (HTTP {response.status_code}), retrying in 10s...")
            time.sleep(10)
    response.raise_for_status()

    out_path = RECORDINGS_DIR / f"{call_sid}.mp3"
    out_path.write_bytes(response.content)
    print(f"  downloaded {out_path.name} ({len(response.content) // 1024} KB)")
    return out_path


def split_channels(mp3_path: Path, call_sid: str) -> tuple[Path, Path]:
    """Split the stereo recording into two mono files via ffmpeg."""
    bot_path = RECORDINGS_DIR / f"{call_sid}-bot.mp3"
    agent_path = RECORDINGS_DIR / f"{call_sid}-agent.mp3"

    # channelsplit is the current filter for this; the older
    # -map_channel flag is deprecated in recent ffmpeg builds.
    #
    # The explicit "-ac 1" on each output matters: without it the MP3
    # encoder upmixes the single-channel filter output back to stereo,
    # which defeats the whole point — you would hand Whisper two files
    # that each still contain both speakers.
    #
    # Channel mapping: on a Twilio dual-channel OUTBOUND call, the left
    # channel [l] carries the CALLED party (the pgai agent) and the
    # right channel [r] carries the CALLER (our bot). So [l] -> agent,
    # [r] -> bot. Getting this backwards swaps the speaker labels in the
    # final transcript.
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(mp3_path),
            "-filter_complex", "[0:a]channelsplit=channel_layout=stereo[l][r]",
            "-map", "[l]", "-ac", "1", str(agent_path),
            "-map", "[r]", "-ac", "1", str(bot_path),
        ],
        check=True,
    )
    return bot_path, agent_path


def transcribe_file(path: Path):
    """Transcribe one mono channel with per-segment timestamps.

    whisper-1 specifically: verbose_json gives segment-level timestamps,
    which is what the [MM:SS] labels in the merged transcript need. The
    newer gpt-4o-transcribe models are sometimes more accurate on clean
    audio but expose different output — check the speech-to-text guide
    before swapping.
    """
    with path.open("rb") as handle:
        return openai_client.audio.transcriptions.create(
            file=handle,
            model="whisper-1",
            response_format="verbose_json",
        )


def format_timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def merge_transcripts(bot_result, agent_result, call_sid: str, label: str) -> str:
    """Interleave both channels chronologically into a readable transcript."""
    turns = []
    for segment in getattr(bot_result, "segments", []) or []:
        turns.append(("Patient (bot)", segment.start, segment.text.strip()))
    for segment in getattr(agent_result, "segments", []) or []:
        turns.append(("Agent (pgai)", segment.start, segment.text.strip()))

    turns.sort(key=lambda turn: turn[1])

    lines = [
        f"Call SID: {call_sid}",
        f"Scenario: {label}",
        f"Caller number: {config.twilio_from_number}",
        f"Called number: {config.pgai_test_number}",
        "",
        "--- TRANSCRIPT ---",
        "",
    ]
    for speaker, start, text in turns:
        if text:
            lines.append(f"[{format_timestamp(start)}] {speaker}: {text}")

    return "\n".join(lines)


def process_call(call_sid: str, label: str = "unknown") -> Path:
    print(f"Processing {call_sid} ({label})")
    mp3_path = download_recording(call_sid)
    bot_path, agent_path = split_channels(mp3_path, call_sid)

    print("  transcribing patient channel...")
    bot_result = transcribe_file(bot_path)
    print("  transcribing agent channel...")
    agent_result = transcribe_file(agent_path)

    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    transcript_path = TRANSCRIPTS_DIR / f"{call_sid}.txt"
    transcript_path.write_text(
        merge_transcripts(bot_result, agent_result, call_sid, label)
    )
    print(f"  wrote {transcript_path.name}\n")
    return transcript_path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.transcribe --all | <callSid>")
        sys.exit(1)

    if sys.argv[1] == "--all":
        if not CALL_LOG.exists():
            print(f"No {CALL_LOG.name} found. Run src.run_suite first.")
            sys.exit(1)

        entries = json.loads(CALL_LOG.read_text())
        placed = [e for e in entries if e["status"] == "placed"]
        print(f"Transcribing {len(placed)} calls\n")

        for entry in placed:
            try:
                process_call(entry["call_sid"], entry["label"])
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED {entry['call_sid']}: {exc}\n")

        print("Next: python -m src.analyze_bugs")
    else:
        process_call(sys.argv[1])


if __name__ == "__main__":
    main()
