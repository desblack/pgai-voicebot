"""Run every scenario in sequence — the 'single command' from the README.
 
Sequential, not parallel, deliberately. Firing a dozen simultaneous calls
at someone else's test system looks like a load test from their side, and
it makes the console output unreadable when you are debugging. One call
at a time with a pause is both the more considerate choice and the more
debuggable one.
 
Call SIDs are written to call_log.json so transcribe.py can pick them up
without you copying them out of the terminal by hand.
 
Usage:
    python -m src.run_suite
"""
 
import json
import time
from pathlib import Path
 
from scenarios.scenarios import SCENARIOS
from src.config import config
from src.place_call import place_call
 
PAUSE_BETWEEN_CALLS_SECONDS = 20
CALL_LOG = Path(__file__).resolve().parent.parent / "call_log.json"
 
 
def main() -> None:
    scenarios = SCENARIOS[: config.max_calls_per_run]
 
    if len(SCENARIOS) > config.max_calls_per_run:
        print(
            f"Warning: {len(SCENARIOS)} scenarios defined but "
            f"MAX_CALLS_PER_RUN={config.max_calls_per_run}. "
            f"Running the first {config.max_calls_per_run} only.\n"
        )
 
    print(f"Running {len(scenarios)} scenarios against {config.pgai_test_number}")
    print(f"Caller ID for all calls: {config.twilio_from_number}")
    print("(That is the number to put on the submission form.)\n")
 
    results = []
 
    for index, scenario in enumerate(scenarios, start=1):
        print(f"[{index}/{len(scenarios)}] ", end="")
        try:
            call = place_call(scenario.id)
            results.append(
                {
                    "scenario_id": scenario.id,
                    "label": scenario.label,
                    "call_sid": call.sid,
                    "status": "placed",
                }
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}")
            results.append(
                {
                    "scenario_id": scenario.id,
                    "label": scenario.label,
                    "error": str(exc),
                    "status": "failed",
                }
            )
 
        # Let the current call finish and its recording finalize before
        # dialing again. Generous relative to the duration cap on purpose.
        if index < len(scenarios):
            print(f"  waiting {PAUSE_BETWEEN_CALLS_SECONDS}s...\n")
            time.sleep(PAUSE_BETWEEN_CALLS_SECONDS)
 
    CALL_LOG.write_text(json.dumps(results, indent=2))
 
    placed = sum(1 for r in results if r["status"] == "placed")
    failed = len(results) - placed
 
    print(f"\n=== Suite complete: {placed} placed, {failed} failed ===")
    print(f"Call SIDs written to {CALL_LOG}")
    if failed:
        print("Re-run failed scenarios individually with src.place_call")
    print("\nNext: python -m src.transcribe --all")
 
 
if __name__ == "__main__":
    main()
 
