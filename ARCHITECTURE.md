# Architecture

## Summary

A batch runner picks a test scenario and asks Twilio to place an outbound call.
When the line connects, Twilio fetches TwiML from the FastAPI server, which
responds with `<Connect><Stream>` — opening a bidirectional WebSocket that
carries live call audio. The server holds a second WebSocket open to OpenAI's
Realtime API, configured with that scenario's patient persona. Audio from the
pgai agent is decoded from telephony mu-law, upsampled, and forwarded into the
Realtime session; the speech the model generates is downsampled back to mu-law
and forwarded onto the call. Twilio records each call dual-channel in parallel.
Afterward, a separate pipeline downloads each recording as MP3, splits the two
channels with ffmpeg, transcribes each independently, merges them by timestamp
into a labeled transcript, and runs an offline grading pass that writes the bug
report.

The two decisions that shaped everything else: **speech-to-speech instead of a
cascaded STT→LLM→TTS pipeline**, because every hop in a cascade adds latency and
the resulting dead air is exactly what makes a call sound robotic — and natural
turn-taking is the criterion graded first, before code is opened. And **bug
detection offline rather than in-call**, because asking one model to
simultaneously play a distracted patient and objectively grade the other party
is two conflicting jobs; separating them keeps the dialogue natural and makes
grading re-runnable, so the criteria can be improved and every transcript
re-analyzed without placing a single new call.

---

*The sections below expand on the trade-offs, alternatives evaluated, and
constraints behind those choices.*

## Why speech-to-speech, and not a cascaded pipeline

The obvious alternative is chaining speech-to-text, then a chat model, then
text-to-speech. It is easier to reason about component by component, and it lets
each stage be swapped independently. I did not use it because every hop adds
latency: transcribe and wait, generate and wait, synthesize and wait. Even fast
implementations stack up to a second or more of dead air per turn, and dead air
is precisely what makes a phone call sound like a machine.

That matters here more than usual, because the evaluation criteria put natural
conversation and sensible turn-taking as priority #1 — graded before the code is
opened. An architecture that is cleaner on paper but produces stilted calls
fails the thing being measured first. The Realtime API does speech understanding
and generation in one hop and handles voice-activity detection server-side, so
turn-taking is driven by actual pauses rather than by my own silence heuristics.

The trade-off is real: I own less of the pipeline, cannot swap the ASR model
independently, and I am exposed to a single vendor's availability and pricing for
the core loop. For a bounded project where conversational realism is the primary
grading criterion, that is the right side of the trade. For a system where
transcript accuracy mattered more than latency, I would revisit it.

## Audio format handling

Twilio Media Streams send and receive 8kHz G.711 mu-law — the standard
telephony format. OpenAI's Realtime API accepts PCM16 at 24kHz as input and can
return PCM16 as output. The server therefore does the conversion on the bridge:
incoming mu-law is decoded to PCM16 and upsampled 8kHz → 24kHz before being
forwarded to OpenAI, and the model's PCM output is downsampled 24kHz → 8kHz and
re-encoded to mu-law on the way back to Twilio. This uses Python's standard
`audioop`, so it needs no extra dependency.

The Realtime API also moved from a beta interface to GA, and most tutorials
still show the beta shape — an `OpenAI-Beta` header, a `-preview-` model name,
flat session keys. The beta shape fails quietly rather than loudly. This code
uses the GA shape: no beta header, a versioned model name, and session config
nested under `session.audio.{input,output}`.

## Why bug detection runs offline

Bug detection is a separate pass over finished transcripts, not something the
in-call model does. Asking one model to simultaneously play a distracted patient
and objectively grade the other party is two conflicting jobs — it would make
the dialogue less natural, which costs points on the criterion evaluated first.

Offline grading is also re-runnable. The grading prompt can be improved and
every transcript re-analyzed without placing a single new call. Given a fixed
budget and a per-minute cost, decoupling "did the call work" from "was the call
handled well" means iterating on the second question is free.

The cost is that an LLM grader misses things a clinical operations person would
catch, and occasionally flags style as substance despite instructions not to.
The consolidated report is a first draft that gets a human pass before
submission.

## Why personas carry a hidden expectation field

Each scenario has a `persona` (sent to the model) and an `expected_behavior`
(never sent — read only by the offline grader). Keeping them separate means the
caller behaves like a patient rather than like something aware it is running a
test. A caller that knows the closed-hours request is a trap will lead the agent
toward the answer; a caller that does not will book the invalid appointment and
say thank you, which is the behavior that actually surfaces the bug.

## Transcription and speaker labeling

Twilio records each call dual-channel, so the two sides arrive on separate
tracks. The pipeline splits them with ffmpeg (forcing mono output, or the
encoder upmixes each track back to stereo and both files end up containing both
speakers) and transcribes each independently. On a dual-channel outbound call,
the left channel carries the called party (the pgai agent) and the right channel
carries the caller (our bot), so labeling comes from which channel the audio was
on rather than from a diarization model guessing. The two transcripts are merged
by timestamp into one readable conversation.

## Scale is a risk budget, not a throughput budget

This system places roughly a dozen calls, ever. Requests per second is not the
interesting number. The interesting numbers are cost per call — roughly $1,
dominated by Realtime audio minutes, with telephony and transcription in the
cents — and the probability of an unbounded loop. Hence hard caps on call count
and call duration, enforced in application code and again at the Twilio layer so
they still hold if the server process dies mid-call, plus a startup assertion
that the dial target matches the assessment number.

## A note on machine detection

An early version passed Twilio's `machine_detection` parameter, intending to
skip voicemail. Because the pgai agent is itself an AI voice, Twilio's detector
classified it as an answering machine and waited for the "message" to finish
before running the stream TwiML — which never happened, so the media stream
never started and the bot stayed silent. Removing machine detection entirely was
the fix: we are deliberately calling an automated agent and want to connect and
stream immediately.

## What I deliberately did not build

No dashboard, no database, no authentication, no retry/queue infrastructure. One
operator runs one batch of calls. In-memory state and a JSON call log are the
correct amount of engineering for that, and the brief explicitly does not want
production infrastructure.
