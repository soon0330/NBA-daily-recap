import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import find_latest_report, short_dirs

ASSETS_DIR = Path(__file__).parent / "assets"
AVATAR_PATH = ASSETS_DIR / "avatar.png"

CARD_SIZE = (1080, 1920)
DEFAULT_BG_COLOR = (18, 18, 23)
DEFAULT_ACCENT_COLOR = (255, 200, 60)
TEXT_COLOR = (245, 245, 245)
FONTS_DIR = Path("C:/Windows/Fonts")

TEAM_COLORS = {
    "Atlanta Hawks": ("#E03A3E", "#C1D32F"),
    "Boston Celtics": ("#062A1F", "#007A33"),
    "Brooklyn Nets": ("#000000", "#FFFFFF"),
    "Charlotte Hornets": ("#1D1160", "#00788C"),
    "Chicago Bulls": ("#1A1A1A", "#CE1141"),
    "Cleveland Cavaliers": ("#860038", "#FDBB30"),
    "Dallas Mavericks": ("#00538C", "#B8C4CA"),
    "Denver Nuggets": ("#0E2240", "#FEC524"),
    "Detroit Pistons": ("#1D42BA", "#C8102E"),
    "Golden State Warriors": ("#1D428A", "#FFC72C"),
    "Houston Rockets": ("#1A1A1A", "#CE1141"),
    "Indiana Pacers": ("#002D62", "#FDBB30"),
    "LA Clippers": ("#1D428A", "#C8102E"),
    "Los Angeles Lakers": ("#552583", "#FDB927"),
    "Memphis Grizzlies": ("#12173F", "#5D76A9"),
    "Miami Heat": ("#0A0A0A", "#F9A01B"),
    "Milwaukee Bucks": ("#00471B", "#EEE1C6"),
    "Minnesota Timberwolves": ("#0C2340", "#236192"),
    "New Orleans Pelicans": ("#0C2340", "#85714D"),
    "New York Knicks": ("#006BB6", "#F58426"),
    "Oklahoma City Thunder": ("#007AC1", "#EF3B24"),
    "Orlando Magic": ("#0077C0", "#C4CED4"),
    "Philadelphia 76ers": ("#006BB6", "#ED174C"),
    "Phoenix Suns": ("#1D1160", "#E56020"),
    "Portland Trail Blazers": ("#1A1A1A", "#E03A3E"),
    "Sacramento Kings": ("#5A2D81", "#63727A"),
    "San Antonio Spurs": ("#1A1A1A", "#C4CED4"),
    "Toronto Raptors": ("#0A0A0A", "#CE1141"),
    "Utah Jazz": ("#002B5C", "#F9A01B"),
    "Washington Wizards": ("#002B5C", "#E31837"),
}


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def colors_for_game(game):
    bg_hex, accent_hex = TEAM_COLORS.get(game["home_team"], (None, None))
    if bg_hex is None:
        return DEFAULT_BG_COLOR, DEFAULT_ACCENT_COLOR
    return hex_to_rgb(bg_hex), hex_to_rgb(accent_hex)


def luminance(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def readable_text_color(background):
    return (20, 20, 20) if luminance(background) > 150 else (255, 255, 255)


def label_color(background, accent):
    return accent if abs(luminance(accent) - luminance(background)) > 70 else TEXT_COLOR


@lru_cache(maxsize=None)
def load_font(size, bold=False):
    candidates = (["arialbd.ttf", "segoeuib.ttf"] if bold else ["arial.ttf", "segoeui.ttf"])
    for name in candidates:
        path = FONTS_DIR / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_text(image, text, x, y, font, fill, alpha=1.0):
    if alpha <= 0:
        return
    bbox = font.getbbox(text)
    tile = Image.new("RGBA", (bbox[2] + 6, bbox[3] + 6), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((0, 0), text, font=font, fill=tuple(fill) + (255,))
    if alpha < 1:
        tile.putalpha(tile.getchannel("A").point(lambda a: int(a * alpha)))
    image.paste(tile, (int(x), int(y)), tile)


def draw_centered(image, text, y, font, fill, alpha=1.0):
    bbox = font.getbbox(text)
    draw_text(image, text, (CARD_SIZE[0] - (bbox[2] - bbox[0])) / 2, y, font, fill, alpha)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def progress(t, start, duration):
    if t is None:
        return 1.0
    return min(max((t - start) / duration, 0.0), 1.0)


def counted(value, t, start, duration):
    return round(value * ease_out(progress(t, start, duration)))


SCORE_CARD_ANIMATION_SECONDS = 1.9
PLAYER_CARD_ANIMATION_SECONDS = 1.5


def linescore_animation_seconds(game, interval):
    return 0.2 + interval * len(game["periods"]) + 0.9


def render_score_card(game, subtitle=None, t=None):
    bg_color, accent = colors_for_game(game)
    accent_color = label_color(bg_color, accent)
    image = Image.new("RGB", CARD_SIZE, bg_color)

    label_font = load_font(48)
    team_font = load_font(70, bold=True)
    score_font = load_font(160, bold=True)
    subtitle_font = load_font(42)

    draw_centered(image, "FINAL", 260, label_font, accent_color)
    draw_centered(image, game["away_team"].upper(), 360, team_font, TEXT_COLOR)
    draw_centered(image, str(counted(game["away_score"], t, 0.2, 0.8)), 460, score_font, TEXT_COLOR)

    draw_centered(image, "AT", 700, label_font, accent_color)

    draw_centered(image, game["home_team"].upper(), 800, team_font, TEXT_COLOR)
    draw_centered(image, str(counted(game["home_score"], t, 0.5, 0.8)), 900, score_font, TEXT_COLOR)

    if game.get("overtime"):
        draw_centered(image, "OVERTIME", 1150, label_font, accent_color, progress(t, 1.2, 0.4))
    if subtitle:
        draw_centered(image, subtitle, 1300, subtitle_font, TEXT_COLOR, progress(t, 1.4, 0.4))
    return image


def render_player_card(performer, t=None):
    bg_color = (20, 16, 10)
    gold = (255, 199, 44)
    image = Image.new("RGB", CARD_SIZE, bg_color)

    label_font = load_font(46)
    team_font = load_font(44)
    stat_number_font = load_font(110, bold=True)
    stat_label_font = load_font(36)

    name_text = performer["name"].upper()
    name_size = 90
    name_font = load_font(name_size, bold=True)
    while name_size > 40 and name_font.getbbox(name_text)[2] > CARD_SIZE[0] - 120:
        name_size -= 4
        name_font = load_font(name_size, bold=True)

    draw_centered(image, "TOP SCORER", 300, label_font, gold)
    draw_centered(image, name_text, 420, name_font, TEXT_COLOR)
    draw_centered(image, performer.get("team", ""), 540, team_font, gold)

    stats = [("PTS", performer["pts"]), ("REB", performer["reb"]), ("AST", performer["ast"])]
    col_width = CARD_SIZE[0] // len(stats)
    for index, (label, value) in enumerate(stats):
        col_center = col_width * index + col_width // 2
        number = str(counted(value, t, 0.1 + 0.2 * index, 0.8))
        number_width = stat_number_font.getbbox(number)[2]
        draw_text(image, number, col_center - number_width / 2, 850, stat_number_font, gold)
        label_width = stat_label_font.getbbox(label)[2]
        draw_text(image, label, col_center - label_width / 2, 1000, stat_label_font, TEXT_COLOR)
    return image


def score_card_subtitle(game):
    if game["deficit_overcome"] >= 8:
        return f"{game['winner']} overcame a {game['deficit_overcome']}-point deficit"
    if game["margin"] <= 3:
        return f"Decided by {game['margin']} point{'s' if game['margin'] != 1 else ''}"
    return None


def render_linescore_card(game, t=None, interval=0.45):
    bg_color, accent_color = colors_for_game(game)
    image = Image.new("RGB", CARD_SIZE, bg_color)
    draw = ImageDraw.Draw(image)

    title_font = load_font(60, bold=True)
    header_font = load_font(40)
    name_font = load_font(44, bold=True)
    number_font = load_font(52)
    total_font = load_font(64, bold=True)

    draw_centered(image, "QUARTER BY QUARTER", 420, title_font, TEXT_COLOR)

    periods = game["periods"] + ["T"]
    name_width = 300
    margin = 40
    column_width = (CARD_SIZE[0] - 2 * margin - name_width) // len(periods)
    table_top = 640
    row_height = 130

    def column_center(index):
        return margin + name_width + column_width * index + column_width // 2

    def column_state(index):
        start = 0.2 + interval * index
        shown = progress(t, start, 0.3)
        return start, shown, (1 - ease_out(shown)) * 24

    for index, label in enumerate(periods):
        _, shown, slide = column_state(index)
        draw_text(image, label, column_center(index) - header_font.getbbox(label)[2] / 2, table_top + slide,
                  header_font, (200, 205, 215), shown)

    rows = [
        (game["away_team"], game["away_quarters"], game["away_score"]),
        (game["home_team"], game["home_quarters"], game["home_score"]),
    ]
    for row_index, (team, quarters, total) in enumerate(rows):
        y = table_top + 130 + row_index * 190
        is_winner = team == game["winner"]
        if is_winner:
            draw.rounded_rectangle(
                (margin - 20, y - 25, CARD_SIZE[0] - margin + 20, y - 25 + row_height + 20),
                radius=24,
                fill=accent_color,
            )
        row_color = readable_text_color(accent_color) if is_winner else TEXT_COLOR
        draw_text(image, team.split()[-1].upper(), margin, y + 8, name_font, row_color)
        for index, value in enumerate(quarters + [total]):
            start, shown, slide = column_state(index)
            is_total = index == len(quarters)
            font = total_font if is_total else number_font
            text = str(counted(total, t, start, 0.8)) if is_total else str(value)
            draw_text(image, text, column_center(index) - font.getbbox(text)[2] / 2, y + slide, font, row_color, shown)
    return image


def build_score_card(game, output_path, subtitle=None):
    render_score_card(game, subtitle).save(output_path)


def build_player_card(performer, output_path):
    render_player_card(performer).save(output_path)


def build_linescore_card(game, output_path):
    render_linescore_card(game).save(output_path)


def ensure_avatar_placeholder():
    if AVATAR_PATH.exists():
        return

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    size = 320
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.ellipse((0, 0, size, size), fill=(35, 38, 48, 255))
    draw.ellipse((60, 150, size - 60, size + 40), fill=(230, 196, 168, 255))
    draw.ellipse((90, 50, size - 90, 220), fill=(230, 196, 168, 255))
    draw.pieslice((80, -10, size - 80, 160), 180, 360, fill=(40, 30, 25, 255))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    image.putalpha(mask)

    image.save(AVATAR_PATH)
    print(f"Created placeholder avatar -> {AVATAR_PATH}")
    print("Swap it anytime: save your own image as assets/avatar.png (same filename).")


def main():
    day_dir, report = find_latest_report()
    if report is None:
        print("No games.json report found. Run fetch_games.py first.")
        sys.exit(1)

    print(f"Using report: {day_dir.name}")

    ensure_avatar_placeholder()

    for game, folder in short_dirs(day_dir, report):
        cards_dir = folder / "cards"
        cards_dir.mkdir(exist_ok=True)
        for stale_card in cards_dir.glob("*.png"):
            stale_card.unlink()

        build_score_card(game, cards_dir / "1_score.png", subtitle=score_card_subtitle(game))
        performer = game.get("top_performer")
        if performer:
            build_player_card(performer, cards_dir / "2_performer.png")
        build_linescore_card(game, cards_dir / "3_linescore.png")
        print(f"Saved cards for {game['matchup']} -> {cards_dir}")

    print("\nAll visuals saved.")


if __name__ == "__main__":
    main()
