# pgai-voicebot

An automated voice bot that calls a live AI phone agent, role-plays realistic
patient scenarios, records and transcribes both sides of every call, and
produces a bug report from what it finds.

Twelve scenarios cover scheduling, rescheduling, cancellation, medication
refills, hours/location/insurance questions, and five deliberate edge cases:
an uncertain medication name, a request for a day the office is closed, a
mid-sentence interruption, an unclear opening request, a frustrated repeat
caller, and two separate requests in one call.

## How it works

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and the reasoning
behind the key decisions. In short: a batch runner asks Twilio to place an
outbound call; when it connects, Twilio opens a bidirectional Media Stream
WebSocket to a FastAPI server; that server bridges the call audio to an OpenAI
Realtime session configured with a patient persona; Twilio records both sides;
and an offline pass transcribes each call and flags bugs.

## Requirements

- Python 3.10+
- `ffmpeg` on PATH (`brew install ffmpeg`)
- A Twilio account with a voice-capable number (trial accounts can only dial
  pre-verified numbers, so this must be an upgraded account)
- An OpenAI API key with Realtime model access
- A public HTTPS tunnel, e.g. [ngrok](https://ngrok.com)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then fill in the real values
```

Start the tunnel in its own terminal and copy the HTTPS forwarding URL into
`PUBLIC_BASE_URL` in `.env` (no trailing slash):

```bash
ngrok http 5050
```

Verify everything before spending anything on calls:

```bash
python -m src.preflight
```

Preflight checks ffmpeg, Twilio auth, that the caller ID is owned by your
account, that the account is not a trial, that the OpenAI key can see the
Realtime model, and that the tunnel reaches your running server.

## Run

The server must be running in its own terminal for the whole session:

```bash
python -m src.server
```

Then, in another terminal, run the full pipeline with one command:

```bash
python -m src.run_all
```

`run_all` runs preflight, places all 12 calls, downloads and transcribes them,
and writes the bug report. It asks for confirmation first, since it places real
billable calls.

Outputs land in `recordings/` (MP3), `transcripts/` (TXT), and
`bug_reports/CONSOLIDATED_BUG_REPORT.md`.

### Running stages individually

Useful when something fails partway and you don't want to re-place calls:

```bash
python -m src.preflight                              # verify credentials
python -m src.place_call 08-closed-hours-edge-case   # one scenario
python -m src.run_suite                              # all calls only
python -m src.transcribe --all                       # transcripts only
python -m src.analyze_bugs                           # bug report only
```

## Recordings

Audio files are not committed to the repository (binary audio bloats git
history). The call recordings for this submission are available here:

**[(https://drive.google.com/file/d/1OyPuWz6cCBSJzGmHJGzbAbB5jEKytv-b/view?usp=sharing)]**

## Safety guardrails

`src/config.py` refuses to start if the target number does not match the
assessment line, if the caller ID is not valid E.164, or if the tunnel is not
HTTPS. Call count and per-call duration are both capped, at the application
layer and again at the Twilio layer, so a looping bug cannot run up telephony
charges. A system that places real phone calls deserves hard limits in code,
not just in a runbook.

## Repository layout

```
pgai-voicebot/
├── ARCHITECTURE.md          design rationale and trade-offs
├── README.md
├── requirements.txt
├── .env.example             every variable and where its value comes from
├── scenarios/
│   └── scenarios.py         12 patient personas + expected behaviors
├── src/
│   ├── config.py            env loading, validation, guardrails
│   ├── preflight.py         credential smoke tests
│   ├── server.py            Twilio <-> OpenAI Realtime audio bridge
│   ├── place_call.py        dial one scenario
│   ├── run_suite.py         dial all scenarios, log call SIDs
│   ├── run_all.py           full pipeline in one command
│   ├── transcribe.py        download, channel-split, transcribe, merge
│   └── analyze_bugs.py      offline bug detection
├── recordings/              MP3s (gitignored; linked above)
├── transcripts/             labeled turn-by-turn text
└── bug_reports/             per-call + consolidated report
```

## Environment variables

See `.env.example` for the full list and where each value comes from. Never
commit `.env`.