import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
MUSIC_DIR = Path(__file__).parent / "assets" / "music"
BARS = 32
CHORD_PROGRESSION = [(9, "minor"), (5, "major"), (0, "major"), (7, "major")]
VARIANTS = [("a", 0, 148), ("b", 5, 152), ("c", 7, 144)]
ARPEGGIO_PATTERN = [0, 1, 2, 3, 2, 1, 2, 3, 0, 1, 2, 3, 4, 3, 2, 1]


def midi_to_hz(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def time_axis(seconds):
    return np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE


def kick():
    t = time_axis(0.24)
    frequency = 45 + 110 * np.exp(-t * 30)
    phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    return np.sin(phase) * np.exp(-t * 13)


def snare(rng):
    t = time_axis(0.22)
    noise = rng.standard_normal(len(t)) * np.exp(-t * 20)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28)
    return 0.8 * noise + 0.5 * tone


def hat(rng):
    t = time_axis(0.05)
    noise = np.diff(rng.standard_normal(len(t)), prepend=0)
    return noise * np.exp(-t * 90) * 0.5


def saw(frequency, seconds):
    t = time_axis(seconds)
    return 2 * ((frequency * t) % 1.0) - 1


def bass_note(frequency, seconds):
    t = time_axis(seconds)
    body = 0.6 * saw(frequency, seconds) + 0.8 * np.sin(2 * np.pi * frequency * t)
    return body * np.exp(-t * 5)


def lead_note(frequency, seconds):
    t = time_axis(seconds)
    return np.tanh(3 * saw(frequency, seconds)) * np.exp(-t * 11)


def pad_chord(notes, seconds):
    t = time_axis(seconds)
    mix = sum(saw(midi_to_hz(n), seconds) + saw(midi_to_hz(n) * 1.004, seconds) for n in notes)
    fade = np.minimum(t / 0.05, 1.0) * np.minimum((seconds - t) / 0.1, 1.0)
    return mix * fade / (2 * len(notes))


def place(buffer, sound, start_seconds, gain):
    start = int(start_seconds * SAMPLE_RATE)
    end = min(start + len(sound), len(buffer))
    if start < len(buffer):
        buffer[start:end] += sound[: end - start] * gain


def chord_tones(root, quality):
    third = 3 if quality == "minor" else 4
    return [root, root + third, root + 7]


def render_track(key_offset, bpm, seed):
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar = beat * 4
    total = int((BARS * bar + 1.0) * SAMPLE_RATE)
    drums = np.zeros(total)
    melodic = np.zeros(total)

    kick_hit, snare_hit, hat_hit = kick(), snare(rng), hat(rng)

    for bar_index in range(BARS):
        bar_start = bar_index * bar
        root_pitch_class, quality = CHORD_PROGRESSION[bar_index % len(CHORD_PROGRESSION)]
        root = 57 + (root_pitch_class - 9) + key_offset
        tones = chord_tones(root, quality)

        for step in range(4):
            place(drums, kick_hit, bar_start + step * beat, 1.0)
        for step in (1, 3):
            place(drums, snare_hit, bar_start + step * beat, 0.55)
        for step in range(16):
            place(drums, hat_hit, bar_start + step * beat / 4, 0.5 if step % 2 else 0.25)

        place(melodic, pad_chord(tones, bar), bar_start, 0.22)

        bass_pattern = [0, 0, 12, 0, 0, 0, 12, 7]
        for step, offset in enumerate(bass_pattern):
            note = bass_note(midi_to_hz(root - 12 + offset), beat / 2 * 0.92)
            place(melodic, note, bar_start + step * beat / 2, 0.6)

        if bar_index >= 2:
            arp_notes = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[0] + 24, tones[1] + 24]
            for step, index in enumerate(ARPEGGIO_PATTERN):
                note = lead_note(midi_to_hz(arp_notes[index]), beat / 4 * 0.95)
                place(melodic, note, bar_start + step * beat / 4, 0.17)

    positions = np.arange(total) / SAMPLE_RATE
    position_in_beat = positions % beat
    duck = 1 - 0.65 * np.exp(-position_in_beat / 0.11)

    mix = drums * 0.85 + melodic * duck
    mix = np.tanh(mix * 1.2)
    return mix / np.max(np.abs(mix)) * 0.89


def write_wav(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes((samples * 32767).astype(np.int16).tobytes())


def generate_all():
    paths = []
    for seed, (name, key_offset, bpm) in enumerate(VARIANTS):
        path = MUSIC_DIR / f"energy_{name}_{bpm}bpm.wav"
        write_wav(path, render_track(key_offset, bpm, seed))
        paths.append(path)
        print(f"Generated {path.name}")
    return paths


def find_tracks():
    tracks = sorted(p for ext in ("wav", "mp3", "m4a", "ogg") for p in MUSIC_DIR.glob(f"*.{ext}"))
    return tracks or generate_all()


if __name__ == "__main__":
    generate_all()
