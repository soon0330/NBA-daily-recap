import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from common import build_title, find_latest_report, short_dirs
from notify import send_message

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "output" / "pipeline.log"
NOT_READY_EXIT_CODE = 3
MAX_ATTEMPTS = 2
STDERR_TAIL_LINES = 6

FETCH_STEP = ("Fetch games and stats", "fetch_games.py")
GENERATION_STEPS = [
    ("Write scripts", "write_script.py"),
    ("Generate narration", "narrate.py"),
    ("Draw cards", "fetch_visuals.py"),
    ("Render videos", "make_video.py"),
]
UPLOAD_STEP = ("Upload to YouTube", "upload_youtube.py")


def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )


def run_step(label, script):
    logging.info("=== %s (%s)", label, script)
    started = time.time()
    result = subprocess.run(
        [sys.executable, "-W", "ignore::DeprecationWarning", str(BASE_DIR / script)],
        cwd=BASE_DIR,
        env={**os.environ, "PYTHONUTF8": "1"},
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - started
    if result.stderr:
        sys.stderr.write(result.stderr)

    if result.returncode == NOT_READY_EXIT_CODE and script == FETCH_STEP[1]:
        logging.info("Today's games are not finished yet. Will check again at the next scheduled run.")
        return False

    if result.returncode != 0:
        tail ="\n".join(result.stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        logging.error("FAILED: %s exited with code %s after %.0fs. Pipeline stopped.", script, result.returncode, elapsed)
        send_message(f"NBA bot FAILED at step: {label} ({script})\n\n{tail}")
        sys.exit(result.returncode)
    logging.info("done in %.0fs", elapsed)
    return True


def blocked_folders(day_dir, report):
    return [(game, folder) for game, folder in short_dirs(day_dir, report) if (folder / "blocked.json").exists()]


def already_uploaded():
    day_dir, report = find_latest_report()
    if report is None:
        return False
    return all((folder / "uploaded.json").exists() for _, folder in short_dirs(day_dir, report))


def summary_message(day_dir, report):
    published, blocked, missing = [], [], []
    for game, folder in short_dirs(day_dir, report):
        marker = folder / "uploaded.json"
        if marker.exists():
            record = json.loads(marker.read_text(encoding="utf-8"))
            publish_at = record.get("publish_at")
            when = f"scheduled {datetime.fromisoformat(publish_at).astimezone():%H:%M}" if publish_at else "public now"
            published.append(
                f"- {build_title(game, report['date'])} ({when})\n  https://www.youtube.com/watch?v={record['video_id']}"
            )
        elif (folder / "blocked.json").exists():
            numbers = json.loads((folder / "blocked.json").read_text(encoding="utf-8"))["unverified_numbers"]
            blocked.append(f"- {game['matchup']} (numbers not in data: {numbers})")
        else:
            missing.append(f"- {game['matchup']}")

    total = len(published) + len(blocked) + len(missing)
    lines = [f"NBA recap for {report['date']}: published {len(published)}/{total}", ""]
    lines += published
    if blocked:
        lines += ["", "Held back by the fact check:"] + blocked
    if missing:
        lines += ["", "Not uploaded:"] + missing
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run the full NBA Shorts pipeline.")
    parser.add_argument("--no-upload", action="store_true", help="stop after rendering the videos")
    parser.add_argument("--date", help="process one specific US game day (YYYY-MM-DD) instead of the latest")
    args = parser.parse_args()
    if args.date:
        os.environ["NBA_DATE"] = args.date

    setup_logging()
    logging.info("Pipeline started")

    if not run_step(*FETCH_STEP):
        return

    if already_uploaded():
        logging.info("Latest game day is already fully uploaded. Nothing new to do.")
        return

    for attempt in range(1, MAX_ATTEMPTS + 1):
        for step in GENERATION_STEPS:
            run_step(*step)

        if args.no_upload:
            logging.info("--no-upload given: videos are rendered but not uploaded.")
            return

        run_step(*UPLOAD_STEP)

        day_dir, report = find_latest_report()
        if not blocked_folders(day_dir, report):
            break
        if attempt < MAX_ATTEMPTS:
            logging.info("Some scripts were held back by the fact check. Regenerating once.")

    day_dir, report = find_latest_report()
    message = summary_message(day_dir, report)
    logging.info("\n%s", message)
    send_message(message)
    logging.info("Pipeline finished")


if __name__ == "__main__":
    main()
