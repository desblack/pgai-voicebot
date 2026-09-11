"""One command: place every call, transcribe them, and write the bug report.
 
    python -m src.run_all
 
The brief asks for a single command after setup, and this is it. The
individual stages remain runnable on their own (src.run_suite,
src.transcribe, src.analyze_bugs) because when something goes wrong
mid-pipeline you want to resume from the failed stage rather than
re-placing a dozen calls.
 
Preflight runs first and aborts on failure. Placing calls is the only
irreversible, billable step here, so it should never start against
credentials that were never verified.
"""
 
import sys
import time
 
from src import analyze_bugs, preflight, run_suite, transcribe
from src.config import config
from scenarios.scenarios import SCENARIOS
 
# Recordings finalize a little after the last call ends. Waiting before
# the download stage avoids a wave of retries on the final call.
SETTLE_SECONDS = 30
 
 
def _banner(step: str, title: str) -> None:
    print(f"\n{'=' * 62}\n{step}  {title}\n{'=' * 62}\n")
 
 
def main() -> None:
    print("Full pipeline: preflight -> calls -> transcripts -> bug report")
    print(f"{len(SCENARIOS)} scenarios, caller {config.twilio_from_number}, "
          f"dialing {config.pgai_test_number}")
    print(f"Estimated cost: roughly ${len(SCENARIOS):.0f} in API and telephony.\n")
 
    response = input("This places real, billable calls. Continue? [y/N] ").strip()
    if response.lower() not in ("y", "yes"):
        print("Aborted. Nothing was called.")
        sys.exit(0)
 
    _banner("[1/4]", "Preflight checks")
    # preflight.main() exits non-zero on failure, which stops us here
    # before anything billable happens.
    preflight.main()
 
    _banner("[2/4]", "Placing calls")
    run_suite.main()
 
    print(f"\nWaiting {SETTLE_SECONDS}s for recordings to finalize...")
    time.sleep(SETTLE_SECONDS)
 
    _banner("[3/4]", "Downloading and transcribing")
    sys.argv = ["transcribe", "--all"]
    transcribe.main()
 
    _banner("[4/4]", "Analyzing for bugs")
    analyze_bugs.main()
 
    _banner("DONE", "Review before submitting")
    print("  recordings/   MP3 audio, both channels per call")
    print("  transcripts/  labeled turn-by-turn text")
    print("  bug_reports/CONSOLIDATED_BUG_REPORT.md")
    print()
    print("Two things the pipeline cannot do for you:")
    print("  1. Listen to 2-3 recordings end to end. Voice quality is graded")
    print("     before code review, so pacing problems matter more than bugs.")
    print("  2. Read the bug report and cut anything that is really a nitpick.")
 
 
if __name__ == "__main__":
    main()
 
