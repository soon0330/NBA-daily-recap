import math
import re
import sys
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_audioclips,
)
from PIL import Image, ImageChops, ImageDraw

from common import find_latest_report, short_dirs, split_into_segments

ASSETS_DIR = Path(__file__).parent / "assets"
FONTS_DIR = Path("C:/Windows/Fonts")

CANVAS_SIZE = (1080, 1920)
AVATAR_WIDTH = 220
AVATAR_POSITION = (30, CANVAS_SIZE[1] - 260)
ZOOM_AMOUNT = 0.05
CAPTION_MAX_WORDS = 9
CAPTION_POSITION = ("center", 1480)
FPS = 30


def find_caption_font():
    for name in ("arialbd.ttf", "segoeuib.ttf", "arial.ttf"):
        path = FONTS_DIR / name
        if path.exists():
            return str(path)
    return None


def card_order(cards_dir):
    score = cards_dir / "1_score.png"
    performer = cards_dir / "2_performer.png"
    linescore = cards_dir / "3_linescore.png"
    hook_card = performer if performer.exists() else score
    return [hook_card, linescore, score]


def load_round_avatar(avatar_path):
    image = Image.open(avatar_path).convert("RGBA")
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((AVATAR_WIDTH, AVATAR_WIDTH), Image.LANCZOS)

    circle = Image.new("L", image.size, 0)
    ImageDraw.Draw(circle).ellipse((0, 0, AVATAR_WIDTH - 1, AVATAR_WIDTH - 1), fill=255)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), circle))
    return np.array(image)


def build_avatar_clip(avatar_path, duration):
    if not avatar_path.exists():
        return None
    return ImageClip(load_round_avatar(avatar_path)).with_duration(duration).with_position(AVATAR_POSITION)


def split_caption_chunks(text, max_words=CAPTION_MAX_WORDS):
    chunks = []
    for sentence in re.findall(r"[^.!?]+[.!?]*", text):
        words = sentence.split()
        if not words:
            continue
        parts = math.ceil(len(words) / max_words)
        size = math.ceil(len(words) / parts)
        for i in range(0, len(words), size):
            chunks.append(" ".join(words[i:i + size]))
    return chunks


def build_caption_clips(text, start, duration, font):
    chunks = split_caption_chunks(text)
    total_words = sum(len(c.split()) for c in chunks)
    clips = []
    offset = 0.0
    for chunk in chunks:
        chunk_duration = duration * len(chunk.split()) / total_words
        caption = TextClip(
            font=font,
            text=chunk,
            font_size=54,
            color="white",
            stroke_color="black",
            stroke_width=3,
            margin=(20, 30),
            method="caption",
            size=(900, None),
            text_align="center",
            horizontal_align="center",
        ).with_duration(chunk_duration).with_start(start + offset).with_position(CAPTION_POSITION)
        clips.append(caption)
        offset += chunk_duration
    return clips


def make_short(folder, font):
    segments = split_into_segments((folder / "script.txt").read_text(encoding="utf-8"))
    audio_paths = sorted(folder.glob("narration_*.mp3"))
    audio_clips = [AudioFileClip(str(p)) for p in audio_paths]
    durations = [c.duration for c in audio_clips]
    total_duration = sum(durations)
    print(f"Narration: {len(audio_clips)} segments, {total_duration:.1f}s total")

    cards = card_order(folder / "cards")

    layers = []
    start = 0.0
    for index, duration in enumerate(durations):
        card = (
            ImageClip(str(cards[min(index, len(cards) - 1)]))
            .with_duration(duration)
            .resized(lambda t, d=duration: 1 + ZOOM_AMOUNT * t / d)
            .with_position("center")
            .with_start(start)
        )
        layers.append(card)
        start += duration

    avatar_clip = build_avatar_clip(ASSETS_DIR / "avatar.png", total_duration)
    if avatar_clip is not None:
        layers.append(avatar_clip)

    start = 0.0
    for text, duration in zip(segments, durations):
        layers.extend(build_caption_clips(text, start, duration, font))
        start += duration

    audio = concatenate_audioclips(audio_clips)
    final = CompositeVideoClip(layers, size=CANVAS_SIZE).with_duration(total_duration).with_audio(audio)

    output_path = folder / "final_video.mp4"
    final.write_videofile(str(output_path), fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast", threads=4)
    final.close()
    for clip in audio_clips:
        clip.close()
    return output_path


def main():
    day_dir, report = find_latest_report()
    if report is None:
        print("No games.json report found. Run fetch_games.py first.")
        sys.exit(1)

    print(f"Using report: {day_dir.name}")

    font = find_caption_font()

    for game, folder in short_dirs(day_dir, report):
        if not list(folder.glob("narration_*.mp3")):
            print(f"Skipping {game['matchup']}: no narration (run write_script.py and narrate.py first).")
            continue

        print(f"\n=== {game['matchup']} ===")
        output_path = make_short(folder, font)
        print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
