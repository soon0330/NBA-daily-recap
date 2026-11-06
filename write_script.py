import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from common import find_latest_report, loser_of, short_dirs

load_dotenv()

MODEL = "gemini-3.5-flash-lite"
TARGET_WORD_COUNT = "85-110"
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 10
PAUSE_BETWEEN_GAMES_SECONDS = 3

SYSTEM_PROMPT = f"""You are a sports storyteller writing the voiceover for a single YouTube Short about ONE NBA game.

Rules:
- Use ONLY the facts given below. Never invent plays, stats, quotes, or storylines that are not in the data.
- Do NOT mention conferences, rivalries, standings, defense, strategy, injuries, crowd, or anything else that is not directly stated in the data. Describe only scores, quarter-by-quarter flow, the top scorer's stat line, comebacks, and overtime.
- Write 100% original wording. Do not imitate any specific commentator, broadcaster, or article.
- Tone: energetic and punchy, like a highlights-reel voiceover.
- Target length: {TARGET_WORD_COUNT} words (about 35-45 seconds spoken aloud).
- Write exactly 3 short paragraphs, separated by one blank line. Each paragraph is matched to an on-screen graphic, so stay strictly on its topic:
  1. HOOK (1-2 sentences): the top scorer's name and stat line, and which team won. Mention nothing about quarters here.
  2. FLOW (2-4 sentences): how the game unfolded period by period using the points-by-period data, including any comeback or overtime. Do not repeat the top scorer's stat line here.
  3. FINISH (1-2 sentences): the final score, then one short line inviting viewers back for tomorrow's story.
- If no top scorer is given, open the HOOK with the result instead.
- Output ONLY the 3 paragraphs, nothing else (no labels, no numbering, no markdown, no quotation marks)."""


def build_prompt(report, game):
    winner = game["winner"]
    lines = [
        f"Date: {report['date']}",
        f"Game: {game['away_team']} (away) at {game['home_team']} (home)",
        f"Final: {game['away_team']} {game['away_score']}, {game['home_team']} {game['home_score']}",
        f"Winner: {winner} (beat {loser_of(game)} by {game['margin']})",
    ]
    if game["overtime"]:
        lines.append("The game went to overtime.")

    lines.append("Points by period:")
    for index, period in enumerate(game["periods"]):
        lines.append(f"  {period}: {game['away_team']} {game['away_quarters'][index]}, {game['home_team']} {game['home_quarters'][index]}")

    if game["deficit_overcome"] >= 5:
        lines.append(f"{winner} trailed by as many as {game['deficit_overcome']} points at the end of a quarter before winning.")

    performer = game.get("top_performer")
    if performer:
        lines.append(
            f"Top scorer of the game: {performer['name']} ({performer['team']}) - "
            f"{performer['pts']} points, {performer['reb']} rebounds, {performer['ast']} assists"
        )

    return "\n".join(lines)


def generate_script(client, report, game):
    prompt = build_prompt(report, game)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=500,
        http_options=types.HttpOptions(timeout=30_000),
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
            return response.text.strip()
        except errors.ServerError as exc:
            if attempt == MAX_RETRIES:
                raise
            wait_seconds = RETRY_BACKOFF_SECONDS * attempt
            print(f"Gemini is overloaded (attempt {attempt}/{MAX_RETRIES}): {exc}")
            print(f"Retrying in {wait_seconds} seconds...")
            time.sleep(wait_seconds)


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Missing GEMINI_API_KEY. Set it in the .env file and try again.")
        sys.exit(1)

    day_dir, report = find_latest_report()
    if report is None:
        print("No games.json report found. Run fetch_games.py first.")
        sys.exit(1)

    print(f"Using report: {day_dir.name}")
    client = genai.Client(api_key=api_key)

    for game, folder in short_dirs(day_dir, report):
        print(f"\n=== {game['matchup']} ===")
        script = generate_script(client, report, game)
        (folder / "script.txt").write_text(script, encoding="utf-8")
        print(f"({len(script.split())} words)\n{script}")
        time.sleep(PAUSE_BETWEEN_GAMES_SECONDS)

    print("\nScripts saved.")


if __name__ == "__main__":
    main()
