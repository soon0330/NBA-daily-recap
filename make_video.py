import math
import random
import re
import sys
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoClip,
    afx,
    concatenate_audioclips,
)
from PIL import Image, ImageChops, ImageDraw

from common import find_latest_report, short_dirs, split_into_segments
from fetch_visuals import (
    PLAYER_CARD_ANIMATION_SECONDS,
    SCORE_CARD_ANIMATION_SECONDS,
    linescore_animation_seconds,
    render_linescore_card,
    render_player_card,
    render_score_card,
    score_card_subtitle,
)
from make_music import find_tracks

ASSETS_DIR = Path(__file__).parent / "assets"
FONTS_DIR = Path("C:/Windows/Fonts")

CANVAS_SIZE = (1080, 1920)
AVATAR_WIDTH = 220
AVATAR_POSITION = (30, CANVAS_SIZE[1] - 260)
MUSIC_VOLUME = 0.2
MUSIC_FADE_SECONDS = 1.5
CAPTION_MAX_WORDS = 9
CAPTION_POSITION = ("center", 1480)
FPS = 30


def find_caption_font():
    for name in ("arialbd.ttf", "segoeuib.ttf", "arial.ttf"):
        path = FONTS_DIR / name
        if path.exists():
            return str(path)
    return None


def animated_card(render, duration, animation_seconds):
    cache = {}

    def make_frame(t):
        if t >= animation_seconds:
            if "final" not in cache:
                cache["final"] = np.array(render(None))
            return cache["final"]
        return np.array(render(t))

    return VideoClip(make_frame, duration=duration)


def build_card_clips(game, durations):
    """One animated card per narration part: hook card, quarter-by-quarter, final score."""
    performer = game.get("top_performer")
    subtitle = score_card_subtitle(game)

    def score_render(t):
        return render_score_card(game, subtitle, t)

    if performer:
        hook = (lambda t: render_player_card(performer, t), PLAYER_CARD_ANIMATION_SECONDS)
    else:
        hook = (score_render, SCORE_CARD_ANIMATION_SECONDS)

    line_duration = durations[1] if len(durations) > 1 else durations[0]
    interval = max(0.45, min(2.0, 0.8 * line_duration / (len(game["periods"]) + 1)))
    linescore = (lambda t: render_linescore_card(game, t, interval), linescore_animation_seconds(game, interval))
    final = (score_render, SCORE_CARD_ANIMATION_SECONDS)
    specs = [hook, linescore, final]

    clips = []
    start = 0.0
    for index, duration in enumerate(durations):
        render, animation_seconds = specs[min(index, len(specs) - 1)]
        clip = animated_card(render, duration, animation_seconds).with_start(start).with_position("center")
        clips.append(clip)
        start += duration
    return clips


def build_music(seed_text, duration):
    path = random.Random(seed_text).choice(find_tracks())
    music = AudioFileClip(str(path)).with_effects([afx.AudioLoop(duration=duration)])
    return music.subclipped(0, duration).with_volume_scaled(MUSIC_VOLUME).with_effects([afx.AudioFadeOut(MUSIC_FADE_SECONDS)])


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


def make_short(folder, game, font):
    segments = split_into_segments((folder / "script.txt").read_text(encoding="utf-8"))
    audio_paths = sorted(folder.glob("narration_*.mp3"))
    audio_clips = [AudioFileClip(str(p)) for p in audio_paths]
    durations = [c.duration for c in audio_clips]
    total_duration = sum(durations)
    print(f"Narration: {len(audio_clips)} segments, {total_duration:.1f}s total")

    layers = build_card_clips(game, durations)

    avatar_clip = build_avatar_clip(ASSETS_DIR / "avatar.png", total_duration)
    if avatar_clip is not None:
        layers.append(avatar_clip)

    start = 0.0
    for text, duration in zip(segments, durations):
        layers.extend(build_caption_clips(text, start, duration, font))
        start += duration

    voice = concatenate_audioclips(audio_clips)
    audio = CompositeAudioClip([voice, build_music(folder.name, total_duration)])
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
        output_path = make_short(folder, game, font)
        print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
