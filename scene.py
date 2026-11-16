import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from fetch_games import ABBREVIATION_TO_FULL_NAME
from fetch_visuals import (
    CARD_SIZE,
    TEAM_COLORS,
    TEXT_COLOR,
    counted,
    draw_centered,
    draw_text,
    hex_to_rgb,
    load_font,
    luminance,
)

CHARACTERS_DIR = Path(__file__).parent / "assets" / "characters"
SUPERSAMPLE = 2
SCENE_TOP = 480
SCENE_HEIGHT = 780
SHOT_ARC_HEIGHT = 200
BACKGROUND = (16, 16, 22)
GOLD = (255, 199, 44)
SKIN = (205, 205, 212)
WOOD = (122, 82, 46)
RIM_COLOR = (255, 110, 30)
BALL_COLOR = (232, 112, 32)

FLOOR_Y = 1180
PLAYER_X = 330
RIM_CENTER = (820, 805)
SHOT_PERIOD = 1.3
CHARACTER_HEIGHT = 520


def jersey_colors(performer):
    team = ABBREVIATION_TO_FULL_NAME.get(performer.get("team", ""))
    background_hex, accent_hex = TEAM_COLORS.get(team, ("#333344", "#FFC72C"))
    background, accent = hex_to_rgb(background_hex), hex_to_rgb(accent_hex)
    if luminance(background) > 45:
        return background, accent
    return accent, background


def lerp(a, b, amount):
    return a + (b - a) * amount


def pose(u):
    """Body pose over one shot cycle (u from 0 to 1): dribble, jump and shoot, follow through."""
    crouch = jump = 0.0
    if u < 0.35:
        crouch = 18 * math.sin(math.pi * u / 0.35)
        arms = 0.1
    elif u < 0.55:
        progress = (u - 0.35) / 0.2
        jump = 70 * math.sin(math.pi * progress)
        arms = progress
    else:
        arms = max(0.1, 1 - (u - 0.55) / 0.45)

    feet_y = FLOOR_Y - jump
    hip_y = feet_y - 170 + crouch
    shoulder_y = hip_y - 150
    hands = {
        "right": (lerp(PLAYER_X + 62, PLAYER_X + 72, arms), lerp(shoulder_y + 150, shoulder_y - 150, arms)),
        "left": (lerp(PLAYER_X - 62, PLAYER_X + 40, arms), lerp(shoulder_y + 150, shoulder_y - 125, arms)),
    }
    return {"feet_y": feet_y, "hip_y": hip_y, "shoulder_y": shoulder_y, "hands": hands, "arms": arms}


def ball_position(u, body):
    release = pose(0.5)["hands"]["right"]
    start = (release[0] + 14, release[1] - 26)
    if u < 0.35:
        bounce = abs(math.sin(math.pi * u / 0.175))
        return PLAYER_X + 84, FLOOR_Y - 34 - bounce * 120
    if u < 0.5:
        hand = body["hands"]["right"]
        return hand[0] + 14, hand[1] - 26
    if u < 0.95:
        progress = (u - 0.5) / 0.45
        x = lerp(start[0], RIM_CENTER[0], progress)
        y = lerp(start[1], RIM_CENTER[1], progress) - SHOT_ARC_HEIGHT * 4 * progress * (1 - progress)
        return x, y
    drop = (u - 0.95) / 0.05
    return RIM_CENTER[0], lerp(RIM_CENTER[1], FLOOR_Y - 34, drop)


@lru_cache(maxsize=None)
def load_character(name):
    path = CHARACTERS_DIR / f"{name}.png"
    if not path.exists():
        return None
    image = Image.open(path).convert("RGBA")
    scale = CHARACTER_HEIGHT * SUPERSAMPLE / image.height
    return image.resize((round(image.width * scale), CHARACTER_HEIGHT * SUPERSAMPLE), Image.LANCZOS)


def draw_scene(performer, t):
    size = (CARD_SIZE[0] * SUPERSAMPLE, SCENE_HEIGHT * SUPERSAMPLE)
    tile = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)

    def p(x, y):
        return (x * SUPERSAMPLE, (y - SCENE_TOP) * SUPERSAMPLE)

    def line(points, width, fill):
        draw.line([p(*pt) for pt in points], fill=fill, width=width * SUPERSAMPLE, joint="curve")

    def circle(center, radius, fill):
        x, y = center
        draw.ellipse([p(x - radius, y - radius), p(x + radius, y + radius)], fill=fill)

    def polygon(points, fill):
        draw.polygon([p(*pt) for pt in points], fill=fill)

    u = (t % SHOT_PERIOD) / SHOT_PERIOD
    body = pose(u)
    main, trim = jersey_colors(performer)

    draw.rectangle([p(0, FLOOR_Y), p(CARD_SIZE[0], SCENE_TOP + SCENE_HEIGHT)], fill=WOOD)
    line([(0, FLOOR_Y), (CARD_SIZE[0], FLOOR_Y)], 6, (205, 150, 90))

    line([(915, 740), (915, FLOOR_Y)], 22, (70, 70, 82))
    draw.rectangle([p(868, 640), p(892, 830)], fill=(236, 236, 242))
    wiggle = 14 * math.sin((u - 0.93) * 60) if u > 0.93 else 0
    rim_left, rim_right = RIM_CENTER[0] - 62, RIM_CENTER[0] + 62
    for index in range(5):
        top_x = lerp(rim_left, rim_right, index / 4)
        bottom_x = RIM_CENTER[0] + (top_x - RIM_CENTER[0]) * 0.5 + wiggle
        line([(top_x, RIM_CENTER[1] + 4), (bottom_x, RIM_CENTER[1] + 90)], 3, (235, 235, 240))
    draw.ellipse([p(rim_left, RIM_CENTER[1] - 12), p(rim_right, RIM_CENTER[1] + 12)], outline=RIM_COLOR, width=8 * SUPERSAMPLE)

    character = load_character(performer["name"])
    if character is not None:
        bob = (FLOOR_Y - body["feet_y"]) * SUPERSAMPLE
        left = int((PLAYER_X - character.width / SUPERSAMPLE / 2) * SUPERSAMPLE)
        top = int((FLOOR_Y - SCENE_TOP) * SUPERSAMPLE - character.height - bob)
        tile.alpha_composite(character, (left, top))
    else:
        feet_y, hip_y, shoulder_y = body["feet_y"], body["hip_y"], body["shoulder_y"]
        for side in (-1, 1):
            line([(PLAYER_X + side * 22, hip_y), (PLAYER_X + side * 30, feet_y - 10)], 30, SKIN)
            draw.ellipse([p(PLAYER_X + side * 30 - 30, feet_y - 14), p(PLAYER_X + side * 30 + 30, feet_y + 8)], fill=(240, 240, 244))
        polygon([(PLAYER_X - 48, hip_y - 30), (PLAYER_X + 48, hip_y - 30), (PLAYER_X + 54, hip_y + 52), (PLAYER_X - 54, hip_y + 52)], main)
        line([(PLAYER_X - 51, hip_y + 46), (PLAYER_X + 51, hip_y + 46)], 8, trim)
        for side in (-1, 1):
            hand = body["hands"]["left" if side == -1 else "right"]
            line([(PLAYER_X + side * 56, shoulder_y + 12), hand], 26, SKIN)
            circle(hand, 15, SKIN)
        polygon([(PLAYER_X - 56, shoulder_y), (PLAYER_X + 56, shoulder_y), (PLAYER_X + 46, hip_y - 25), (PLAYER_X - 46, hip_y - 25)], main)
        line([(PLAYER_X - 50, shoulder_y + 10), (PLAYER_X + 50, shoulder_y + 10)], 9, trim)
        circle((PLAYER_X, shoulder_y - 58), 40, SKIN)
        label = performer.get("team", "")
        label_font = load_font(34 * SUPERSAMPLE, bold=True)
        label_box = label_font.getbbox(label)
        draw.text((p(PLAYER_X, 0)[0] - label_box[2] / 2, p(0, shoulder_y + 40)[1]), label, font=label_font, fill=readable_on(main))

    ball = ball_position(u, body)
    circle(ball, 30, BALL_COLOR)
    draw.ellipse([p(ball[0] - 30, ball[1] - 30), p(ball[0] + 30, ball[1] + 30)], outline=(40, 20, 10), width=3 * SUPERSAMPLE)
    line([(ball[0] - 30, ball[1]), (ball[0] + 30, ball[1])], 3, (40, 20, 10))
    line([(ball[0], ball[1] - 30), (ball[0], ball[1] + 30)], 3, (40, 20, 10))

    if u >= 0.93:
        burst = (u - 0.93) / 0.07
        for index in range(10):
            angle = index * math.pi / 5
            start = 40 + 20 * burst
            end = 70 + 60 * burst
            line([
                (RIM_CENTER[0] + math.cos(angle) * start, RIM_CENTER[1] + math.sin(angle) * start),
                (RIM_CENTER[0] + math.cos(angle) * end, RIM_CENTER[1] + math.sin(angle) * end),
            ], 6, GOLD)

    return tile.resize((CARD_SIZE[0], SCENE_HEIGHT), Image.LANCZOS)


def readable_on(color):
    return (20, 20, 20) if luminance(color) > 150 else (255, 255, 255)


def render_scoring_scene(performer, t):
    image = Image.new("RGB", CARD_SIZE, BACKGROUND)

    label_font = load_font(46)
    team_font = load_font(44)
    number_font = load_font(96, bold=True)
    stat_label_font = load_font(34)

    name_text = performer["name"].upper()
    name_size = 90
    name_font = load_font(name_size, bold=True)
    while name_size > 40 and name_font.getbbox(name_text)[2] > CARD_SIZE[0] - 120:
        name_size -= 4
        name_font = load_font(name_size, bold=True)

    draw_centered(image, "TOP SCORER", 200, label_font, GOLD)
    draw_centered(image, name_text, 290, name_font, TEXT_COLOR)
    draw_centered(image, performer.get("team", ""), 410, team_font, GOLD)

    scene = draw_scene(performer, t)
    image.paste(scene, (0, SCENE_TOP), scene)

    stats = [("PTS", performer["pts"]), ("REB", performer["reb"]), ("AST", performer["ast"])]
    column_width = CARD_SIZE[0] // len(stats)
    for index, (label, value) in enumerate(stats):
        center = column_width * index + column_width // 2
        number = str(counted(value, t, 0.2 + 0.4 * index, 1.6))
        draw_text(image, number, center - number_font.getbbox(number)[2] / 2, 1295, number_font, GOLD)
        draw_text(image, label, center - stat_label_font.getbbox(label)[2] / 2, 1405, stat_label_font, TEXT_COLOR)
    return image
