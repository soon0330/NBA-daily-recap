import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.balldontlie.io/v1"
OUTPUT_DIR = Path(__file__).parent / "output"
MAX_LOOKBACK_DAYS = 7
NOT_READY_EXIT_CODE = 3
API_PAUSE_SECONDS = 13
MAX_FEATURED_GAMES = 4
QUARTERS = ["q1", "q2", "q3", "q4"]

ABBREVIATION_TO_FULL_NAME = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "LA Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}


def get_games(date_str, api_key):
    response = requests.get(
        f"{API_BASE}/games",
        params={"dates[]": [date_str]},
        headers={"Authorization": api_key},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["data"]


def find_latest_complete_day(api_key):
    """Returns (date, games) for the newest US game day whose games are all final.
    Returns (date, None) when today's US game day is still in progress."""
    today_us = datetime.now(ZoneInfo("America/New_York")).date()
    for days_back in range(MAX_LOOKBACK_DAYS + 1):
        date_str = (today_us - timedelta(days=days_back)).isoformat()
        games = [g for g in get_games(date_str, api_key) if not g.get("postponed")]
        states = {g.get("status_state") for g in games}
        if games and states == {"final"}:
            return date_str, games
        if games and states != {"scheduled"} and days_back == 0:
            return date_str, None
        if days_back >= 3:
            time.sleep(API_PAUSE_SECONDS)
    return None, []


def summarize_game(game):
    home = game["home_team"]
    away = game["visitor_team"]
    home_score = game["home_team_score"]
    away_score = game["visitor_team_score"]
    margin = abs(home_score - away_score)
    overtime = game["period"] > 4
    winner = home["full_name"] if home_score > away_score else away["full_name"]

    periods = ["Q1", "Q2", "Q3", "Q4"]
    home_quarters = [game.get(f"home_{q}") or 0 for q in QUARTERS]
    away_quarters = [game.get(f"visitor_{q}") or 0 for q in QUARTERS]
    for ot_number in (1, 2, 3):
        home_ot = game.get(f"home_ot{ot_number}")
        away_ot = game.get(f"visitor_ot{ot_number}")
        if home_ot is not None or away_ot is not None:
            periods.append("OT" if ot_number == 1 else f"OT{ot_number}")
            home_quarters.append(home_ot or 0)
            away_quarters.append(away_ot or 0)

    return {
        "matchup": f"{away['full_name']} @ {home['full_name']}",
        "home_team": home["full_name"],
        "away_team": away["full_name"],
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "margin": margin,
        "overtime": overtime,
        "periods_played": game["period"],
        "periods": periods,
        "home_quarters": home_quarters,
        "away_quarters": away_quarters,
        "deficit_overcome": biggest_deficit_overcome(game),
    }


def pick_headline_game(summaries):
    overtime_games = [g for g in summaries if g["overtime"]]
    if overtime_games:
        return min(overtime_games, key=lambda g: g["margin"])
    return min(summaries, key=lambda g: g["margin"])


def biggest_deficit_overcome(game):
    home_cum = 0
    away_cum = 0
    winner_is_home = game["home_team_score"] > game["visitor_team_score"]
    max_deficit = 0
    for q in QUARTERS:
        home_cum += game.get(f"home_{q}") or 0
        away_cum += game.get(f"visitor_{q}") or 0
        deficit = (away_cum - home_cum) if winner_is_home else (home_cum - away_cum)
        max_deficit = max(max_deficit, deficit)
    return max_deficit


def find_biggest_comeback(games):
    best_game, best_deficit = None, 0
    for game in games:
        deficit = biggest_deficit_overcome(game)
        if deficit > best_deficit:
            best_game, best_deficit = game, deficit

    if best_game is None:
        return None

    home = best_game["home_team"]
    away = best_game["visitor_team"]
    winner = home["full_name"] if best_game["home_team_score"] > best_game["visitor_team_score"] else away["full_name"]
    return {
        "matchup": f"{away['full_name']} @ {home['full_name']}",
        "winner": winner,
        "deficit_overcome": best_deficit,
    }


def find_game_performers(date_str):
    """Returns {frozenset({home_full_name, away_full_name}): performer_dict} for every game that date."""
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2, scoreboardv2
    except ImportError:
        print("nba_api not installed, skipping per-game top performer lookup.")
        return {}

    try:
        board = scoreboardv2.ScoreboardV2(game_date=date_str, league_id="00", day_offset=0)
        game_ids = board.game_header.get_data_frame()["GAME_ID"].tolist()
    except Exception as exc:
        print(f"nba_api scoreboard lookup failed, skipping top performers: {exc}")
        return {}

    performers = {}
    for game_id in game_ids:
        try:
            box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
            players = box.player_stats.get_data_frame()
        except Exception as exc:
            print(f"nba_api box score lookup failed for game {game_id}, skipping: {exc}")
            continue
        finally:
            time.sleep(0.6)

        if players.empty:
            continue

        top_row = players.loc[players["PTS"].idxmax()]
        performer = {
            "name": top_row["PLAYER_NAME"],
            "team": top_row.get("TEAM_ABBREVIATION", ""),
            "pts": int(top_row["PTS"]),
            "reb": int(top_row["REB"]),
            "ast": int(top_row["AST"]),
        }

        team_abbrs = players["TEAM_ABBREVIATION"].dropna().unique().tolist()
        full_names = frozenset(ABBREVIATION_TO_FULL_NAME.get(abbr, abbr) for abbr in team_abbrs)
        if len(full_names) == 2:
            performers[full_names] = performer

    return performers


def pick_featured_games(summaries, headline, comeback):
    featured = [headline]

    if comeback:
        comeback_game = next((g for g in summaries if g["matchup"] == comeback["matchup"]), None)
        if comeback_game and comeback_game not in featured:
            featured.append(comeback_game)

    by_scoring = sorted(
        (g for g in summaries if g.get("top_performer")),
        key=lambda g: g["top_performer"]["pts"],
        reverse=True,
    )
    by_closeness = sorted(summaries, key=lambda g: g["margin"])
    for game in by_scoring + by_closeness:
        if len(featured) >= MAX_FEATURED_GAMES:
            break
        if game not in featured:
            featured.append(game)

    return featured[:MAX_FEATURED_GAMES]


def build_report(date_str, games):
    summaries = [summarize_game(g) for g in games]

    performers = find_game_performers(date_str)
    for summary in summaries:
        key = frozenset({summary["home_team"], summary["away_team"]})
        summary["top_performer"] = performers.get(key)

    headline = pick_headline_game(summaries)
    comeback = find_biggest_comeback(games)

    return {
        "date": date_str,
        "games": summaries,
        "headline_game": headline,
        "biggest_comeback": comeback,
        "featured_games": pick_featured_games(summaries, headline, comeback),
    }


def main():
    api_key = os.getenv("BALLDONTLIE_API_KEY")
    if not api_key:
        print("Missing BALLDONTLIE_API_KEY. Set it in the .env file and try again.")
        sys.exit(1)

    date_str, games = find_latest_complete_day(api_key)
    if games is None:
        print(f"Games for {date_str} (US date) are still in progress. Try again later.")
        sys.exit(NOT_READY_EXIT_CODE)
    if not games:
        print(f"No finished NBA games found in the last {MAX_LOOKBACK_DAYS} days (likely off-season).")
        sys.exit(1)

    report = build_report(date_str, games)

    day_dir = OUTPUT_DIR / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    report_path = day_dir / "games.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Game date: {date_str}")
    print(f"{len(report['games'])} game(s):\n")
    for g in report["games"]:
        ot_tag = " (OT)" if g["overtime"] else ""
        print(f"  {g['matchup']}: {g['away_score']} - {g['home_score']}{ot_tag}  Winner: {g['winner']}")
        performer = g.get("top_performer")
        if performer:
            print(
                f"    Top performer: {performer['name']} ({performer['team']}) - "
                f"{performer['pts']} PTS, {performer['reb']} REB, {performer['ast']} AST"
            )

    headline = report["headline_game"]
    print(f"\nHeadline game: {headline['matchup']} ({headline['away_score']}-{headline['home_score']})")

    comeback = report["biggest_comeback"]
    if comeback:
        print(f"Biggest comeback: {comeback['winner']} trailed by {comeback['deficit_overcome']} points in {comeback['matchup']} before winning")
    else:
        print("No notable comeback tonight.")

    featured_names = ", ".join(g["matchup"] for g in report["featured_games"])
    print(f"\nOne Short will be made for each featured game ({len(report['featured_games'])}): {featured_names}")

    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
