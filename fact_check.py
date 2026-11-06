import re

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
MIN_CHECKED_NUMBER = 5


def extract_numbers(text):
    """Returns every number in the text, whether written as digits or spelled out in words."""
    numbers = [int(n) for n in re.findall(r"\d+", text)]

    current, found = 0, False
    for token in re.findall(r"[a-z]+", re.sub(r"\d+", " ", text.lower())):
        if token in UNITS:
            current += UNITS[token]
            found = True
        elif token in TENS:
            current += TENS[token]
            found = True
        elif token == "hundred":
            current = (current or 1) * 100
            found = True
        elif token == "and" and found:
            continue
        else:
            if found:
                numbers.append(current)
            current, found = 0, False
    if found:
        numbers.append(current)
    return numbers


def allowed_numbers(game):
    allowed = {game["home_score"], game["away_score"], game["margin"], game["deficit_overcome"]}

    home_total = away_total = 0
    for home_points, away_points in zip(game["home_quarters"], game["away_quarters"]):
        home_total += home_points
        away_total += away_points
        allowed.update({home_points, away_points, abs(home_points - away_points)})
        allowed.update({home_total, away_total, abs(home_total - away_total)})

    performer = game.get("top_performer")
    if performer:
        allowed.update({performer["pts"], performer["reb"], performer["ast"]})
    return allowed


def check_script(game, script_text):
    """Returns the numbers in the script that cannot be traced back to the game data."""
    allowed = allowed_numbers(game)
    unverified = [n for n in extract_numbers(script_text) if n >= MIN_CHECKED_NUMBER and n not in allowed]
    return sorted(set(unverified))
