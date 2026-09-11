"""The audio bridge: Twilio Media Streams <-> OpenAI Realtime API.

Flow of a single call:

  1. place_call.py asks Twilio to dial the test line, telling it to fetch
     call instructions from /twiml/{scenario_id} on this server.
  2. When the line connects, Twilio requests that URL. We answer with
     TwiML containing <Connect><Stream>, which tells Twilio to open a
     WebSocket back to /media-stream and pipe live call audio through it
     in both directions.
  3. On that WebSocket we receive the pgai agent's audio as base64
     G.711 mu-law frames (~20ms each).
  4. For each call we also open our own WebSocket out to OpenAI's
     Realtime API, configured with this scenario's persona. We forward
     the agent's audio in, and forward the model's spoken replies back
     out to Twilio. That relay is this file.
  5. Twilio records the call dual-channel in parallel, so transcription
     later has both sides already separated.

Audio conversion on both legs: Twilio speaks 8kHz G.711 mu-law, but the
Realtime API rejects mu-law entirely — its input formats are PCM16, wav,
mp3, opus, and PCM16 must be 24kHz. So the media handler decodes mu-law
and upsamples 8kHz->24kHz on the way in, and the relay downsamples
24kHz->8kHz and re-encodes mu-law on the way out. This uses the stdlib
audioop module (no extra dependency).

Note: audioop is deprecated and removed in Python 3.13. This project
targets 3.10-3.12. On 3.13+, swap the audioop calls for a maintained
resampler such as soxr plus numpy, or the audioop-lts backport.
"""

import asyncio
import audioop
import base64
import json

import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocketDisconnect

from scenarios.scenarios import get_scenario
from src.config import config

app = FastAPI()

OPENAI_REALTIME_URL = (
    f"wss://api.openai.com/v1/realtime?model={config.openai_realtime_model}"
)


@app.get("/health")
async def health() -> dict:
    """Trivial endpoint to confirm the tunnel reaches this process."""
    return {"status": "ok"}


@app.api_route("/twiml/{scenario_id}", methods=["GET", "POST"])
async def twiml(scenario_id: str) -> HTMLResponse:
    """Twilio fetches this once the outbound call connects.

    The <Parameter> element rides along to the WebSocket handler so it
    knows which persona to load for this particular call.
    """
    stream_url = f"{config.websocket_base_url}/media-stream"
    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}">
      <Parameter name="scenarioId" value="{scenario_id}" />
    </Stream>
  </Connect>
</Response>"""
    return HTMLResponse(content=response, media_type="text/xml")


@app.websocket("/media-stream")
async def media_stream(twilio_ws: WebSocket) -> None:
    """One connection per call. Bridges Twilio audio to OpenAI and back."""
    await twilio_ws.accept()
    print("Twilio media stream connected")

    stream_sid: str | None = None
    scenario = None
    openai_ws = None
    relay_task: asyncio.Task | None = None
    timeout_task: asyncio.Task | None = None

    async def hang_up_after_timeout() -> None:
        """Hard duration cap.

        If the persona and the pgai agent somehow talk in circles, this
        guarantees the call — and the per-minute cost — still ends.
        Twilio enforces its own cap too (see place_call.py); this is the
        belt to that suspenders.
        """
        await asyncio.sleep(config.max_call_duration_seconds)
        print(
            f"Hard duration cap ({config.max_call_duration_seconds}s) reached. "
            f"Closing stream."
        )
        await twilio_ws.close()

    async def relay_openai_to_twilio() -> None:
        """Forward the model's generated speech back onto the phone call."""
        try:
            async for raw in openai_ws:
                event = json.loads(raw)
                etype = event.get("type", "")

                # TEMP DIAGNOSTIC: log every event type except the
                # high-frequency audio deltas, so we can see whether the
                # session was accepted and whether the model ever starts
                # a response. Remove once the audio path is confirmed.
                if etype not in ("response.output_audio.delta", "response.audio.delta"):
                    print(f"  [openai] {etype}")
                    if etype in ("session.updated", "session.created"):
                        pass
                    if etype == "response.done":
                        print(f"  [openai] response.done detail: {json.dumps(event)[:400]}")

                # Audio deltas from OpenAI are 24kHz PCM16 (base64). Twilio
                # wants 8kHz mu-law, so reverse the inbound conversion:
                # downsample 24kHz -> 8kHz, then encode PCM16 -> mu-law.
                # response.output_audio.delta is the GA event name;
                # response.audio.delta is kept as a fallback for the beta
                # event name in case of a model/version difference.
                if etype in (
                    "response.output_audio.delta",
                    "response.audio.delta",
                ):
                    delta = event.get("delta")
                    if delta and stream_sid:
                        pcm24k = base64.b64decode(delta)
                        pcm8k, _ = audioop.ratecv(pcm24k, 2, 1, 24000, 8000, None)
                        mulaw = audioop.lin2ulaw(pcm8k, 2)
                        await twilio_ws.send_text(
                            json.dumps(
                                {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": base64.b64encode(mulaw).decode("ascii")
                                    },
                                }
                            )
                        )

                # When the caller (our persona) starts talking over the
                # agent, tell Twilio to drop any of our audio it has
                # buffered but not yet played. Without this, an
                # interruption leaves stale speech queued and the call
                # audio desynchronizes — which matters most in the
                # barge-in scenario we deliberately test.
                elif etype == "input_audio_buffer.speech_started":
                    if stream_sid:
                        await twilio_ws.send_text(
                            json.dumps({"event": "clear", "streamSid": stream_sid})
                        )

                elif etype == "error":
                    print(f"  [openai] *** ERROR *** {json.dumps(event.get('error'))}")

        except websockets.exceptions.ConnectionClosed:
            print("OpenAI Realtime connection closed")
        except Exception as exc:  # noqa: BLE001
            print(f"Relay error (OpenAI->Twilio): {exc}")

    try:
        while True:
            message = json.loads(await twilio_ws.receive_text())
            event = message.get("event")

            # TEMP DIAGNOSTIC: log every Twilio event so we can see how
            # far the handshake gets. Remove once audio is confirmed.
            print(f"  [twilio] event={event}")

            if event == "start":
                stream_sid = message["start"]["streamSid"]
                scenario_id = message["start"]["customParameters"]["scenarioId"]
                scenario = get_scenario(scenario_id)
                print(f"Call started — scenario {scenario.id}: {scenario.label}")

                print("  [server] connecting to OpenAI Realtime...")
                openai_ws = await websockets.connect(
                    OPENAI_REALTIME_URL,
                    additional_headers={
                        "Authorization": f"Bearer {config.openai_api_key}"
                    },
                )
                print("  [server] OpenAI WebSocket connected")

                await configure_session(openai_ws, scenario)

                relay_task = asyncio.create_task(relay_openai_to_twilio())
                timeout_task = asyncio.create_task(hang_up_after_timeout())

            elif event == "media":
                # Twilio sends 8kHz mu-law. OpenAI's Realtime API rejects
                # mu-law outright — its only input formats are PCM16, wav,
                # mp3, opus — and PCM16 input must be 24kHz. So we decode
                # mu-law to 16-bit PCM, then upsample 8kHz -> 24kHz before
                # forwarding. audioop is in the standard library, so this
                # needs no extra dependency.
                if openai_ws is not None:
                    mulaw = base64.b64decode(message["media"]["payload"])
                    pcm8k = audioop.ulaw2lin(mulaw, 2)  # mu-law -> PCM16 @ 8kHz
                    pcm24k, _ = audioop.ratecv(pcm8k, 2, 1, 8000, 24000, None)
                    await openai_ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(pcm24k).decode("ascii"),
                            }
                        )
                    )

            elif event == "stop":
                print("Twilio media stream stopped")
                break

    except WebSocketDisconnect:
        print("Twilio websocket disconnected")
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"Media stream error: {exc}")
        traceback.print_exc()
    finally:
        for task in (relay_task, timeout_task):
            if task is not None and not task.done():
                task.cancel()
        if openai_ws is not None:
            await openai_ws.close()


async def configure_session(openai_ws, scenario) -> None:
    """Set the persona, voice, audio formats, and turn-taking behavior.

    NOTE ON API VERSION: the Realtime API moved from a beta interface to
    GA. The beta shape — an "OpenAI-Beta: realtime=v1" header, a
    "-preview-" model name, and flat modalities/input_audio_format keys
    — is what most tutorials and blog posts still show, and using it
    fails quietly rather than loudly. This is the GA shape: no beta
    header, versioned model name, config nested under
    session.audio.{input,output}.
    """
    await openai_ws.send(
        json.dumps(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": scenario.persona,
                    "audio": {
                        "input": {
                            # PCM16 at 24kHz. The Realtime API rejects
                            # mu-law (audio/pcmu) outright, so server.py
                            # decodes Twilio's mu-law and upsamples to
                            # this format before forwarding.
                            "format": {"type": "audio/pcm", "rate": 24000},
                            # Server-side voice activity detection. These
                            # numbers are the main lever on whether
                            # turn-taking sounds human: silence_duration_ms
                            # is how long a pause must be before the
                            # persona decides it's their turn. Too low and
                            # it talks over the agent; too high and there
                            # is dead air. 600ms is a reasonable starting
                            # point — tune it after hearing real calls.
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 600,
                            },
                        },
                        "output": {
                            # PCM16 at 24kHz. server.py downsamples this
                            # to 8kHz mu-law on the way back to Twilio.
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "voice": "alloy",
                        },
                    },
                },
            }
        )
    )

    # A real patient doesn't sit in silence waiting to be addressed.
    # Prompt the model to open the conversation in character.
    await openai_ws.send(json.dumps({"type": "response.create"}))
    print("  [server] session configured, response.create sent")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5050)
