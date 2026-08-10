#!/usr/bin/env python3
"""
Autonomous Job Hunter Agent — Entry Point
==========================================
Run modes:
    python main.py                    → Single run (test everything)
    python main.py --daily            → Run once per day at 08:00
    python main.py --daily --hour 9   → Run once per day at 09:00
    python main.py --telegram         → Enable Telegram notifications

Set API keys via environment variables:
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHAT_ID="..."
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from pipeline import JobHunterPipeline


def fix_windows_console_encoding():
    """
    On Windows, the console's default codepage (e.g. cp1252) often can't
    encode the emoji used in log/print output, which crashes with
    UnicodeEncodeError. Force stdout/stderr to UTF-8 so those characters
    print correctly instead. No-op on other platforms.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            # Stream doesn't support reconfigure (e.g. captured/piped
            # in some environments) — leave it as-is.
            pass


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s │ %(name)-24s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="🎯 Autonomous Job Hunter Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--daily", action="store_true",
        help="Run once per day instead of a single run",
    )
    parser.add_argument(
        "--hour", type=int, default=8,
        help="Hour to run daily (24h format, default: 8 → 08:00)",
    )
    parser.add_argument(
        "--telegram", action="store_true",
        help="Enable Telegram notifications",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    fix_windows_console_encoding()
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger("main")

    logger.info("🚀 Initializing Job Hunter Agent...")
    pipeline = JobHunterPipeline(use_telegram=args.telegram)

    if args.daily:
        pipeline.run_daily(run_at_hour=args.hour)
    else:
        results = pipeline.run_once()

        # Print summary
        print("\n" + "─" * 60)
        print("  PIPELINE SUMMARY")
        print("─" * 60)
        for r in results:
            status = "✅" if r.success else "❌"
            n_contacts = len(r.outreach_list)
            error_info = f" ({r.error})" if r.error else ""
            print(
                f"  {status}  {r.job.company:15s} │ {r.job.title:30s} "
                f"│ {n_contacts} contact(s){error_info}"
            )
        print("─" * 60)
        print(
            f"  Total: {len(results)} │ "
            f"Success: {sum(1 for r in results if r.success)} │ "
            f"Contacts found: {sum(len(r.outreach_list) for r in results)}"
        )
        print("─" * 60 + "\n")


if __name__ == "__main__":
    main()
