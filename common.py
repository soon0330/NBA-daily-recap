import json
import math
import os
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
TITLE_MAX_LENGTH = 100


def find_latest_report():
    """Returns the newest game-day report, or the one named by NBA_DATE (YYYY-MM-DD) when that is set."""
    target_date = os.getenv("NBA_DATE")
    day_dirs = sorted((p for p in OUTPUT_DIR.glob("*") if p.is_dir()), reverse=True)
    if target_date:
        day_dirs = [p for p in day_dirs if p.name == target_date]
    for day_dir in day_dirs:
        report_path = day_dir / "games.json"
        if report_path.exists():
            return day_dir, json.loads(report_path.read_text(encoding="utf-8"))
    return None, None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def short_dirs(day_dir, report):
    """Returns [(game, folder)] for every featured game, creating each folder."""
    pairs = []
    for index, game in enumerate(report["featured_games"], start=1):
        folder = day_dir / "shorts" / f"{index:02d}_{slugify(game['matchup'])}"
        folder.mkdir(parents=True, exist_ok=True)
        pairs.append((game, folder))
    return pairs


def split_into_segments(script, count=3):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", script.strip()) if p.strip()]
    if len(paragraphs) == count:
        return paragraphs

    sentences = [s.strip() for s in re.findall(r"[^.!?]+[.!?]*", " ".join(paragraphs)) if s.strip()]
    per_group = math.ceil(len(sentences) / count)
    groups = [" ".join(sentences[i * per_group:(i + 1) * per_group]) for i in range(count)]
    return [g for g in groups if g]


def loser_of(game):
    return game["away_team"] if game["winner"] == game["home_team"] else game["home_team"]


def score_pair(game):
    return max(game["home_score"], game["away_score"]), min(game["home_score"], game["away_score"])


def build_title(game, date_str):
    winner_score, loser_score = score_pair(game)
    ot_tag = " (OT)" if game["overtime"] else ""
    result = f"{game['winner']} beat {loser_of(game)} {winner_score}-{loser_score}{ot_tag}"

    performer = game.get("top_performer")
    if performer:
        stat_line = f"{performer['pts']}+{performer['reb']}+{performer['ast']}"
        headline = f"{performer['name']} {stat_line}! {result}"
    else:
        headline = result

    title = f"{headline} | NBA Recap {date_str}"
    return title if len(title) <= TITLE_MAX_LENGTH else headline[:TITLE_MAX_LENGTH]


def build_description(game, date_str):
    winner_score, loser_score = score_pair(game)
    ot_tag = " (OT)" if game["overtime"] else ""
    lines = [
        f"{game['matchup']} - {date_str}",
        f"Final: {game['away_team']} {game['away_score']}, {game['home_team']} {game['home_score']}{ot_tag}",
    ]

    performer = game.get("top_performer")
    if performer:
        lines.append(
            f"Top performer: {performer['name']} ({performer['team']}) - "
            f"{performer['pts']} PTS, {performer['reb']} REB, {performer['ast']} AST"
        )
    if game.get("deficit_overcome", 0) >= 8:
        lines.append(f"{game['winner']} overcame a {game['deficit_overcome']}-point deficit.")

    lines += [
        "",
        "Commentary and visuals in this video are AI-generated from public NBA game data.",
        "#Shorts #NBA #basketball",
    ]
    return "\n".join(lines)


def build_tags(game):
    tags = ["NBA", "basketball", "NBA recap", "NBA highlights", "Shorts", game["home_team"], game["away_team"]]
    performer = game.get("top_performer")
    if performer:
        tags.append(performer["name"])
    return tags
