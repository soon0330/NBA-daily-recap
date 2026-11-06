import asyncio
import sys

import edge_tts

from common import find_latest_report, short_dirs, split_into_segments

VOICE = "en-US-GuyNeural"
RATE = "+8%"


async def synthesize(text, output_path):
    communicate = edge_tts.Communicate(text, voice=VOICE, rate=RATE)
    await communicate.save(str(output_path))


def main():
    day_dir, report = find_latest_report()
    if report is None:
        print("No games.json report found. Run fetch_games.py first.")
        sys.exit(1)

    print(f"Using report: {day_dir.name}")

    for game, folder in short_dirs(day_dir, report):
        script_path = folder / "script.txt"
        if not script_path.exists():
            print(f"Skipping {game['matchup']}: no script.txt (run write_script.py first).")
            continue

        for old_file in folder.glob("narration_*.mp3"):
            old_file.unlink()

        segments = split_into_segments(script_path.read_text(encoding="utf-8"))
        for index, text in enumerate(segments, start=1):
            asyncio.run(synthesize(text, folder / f"narration_{index}.mp3"))
        print(f"Saved {len(segments)} narration segments for {game['matchup']}")


if __name__ == "__main__":
    main()
