# NBA Daily Shorts Bot

Automatically turns each day's NBA results into YouTube Shorts. For every standout game it builds a ~35 second vertical video with an AI-written voiceover, on-screen stat cards and captions, uploads it to YouTube, and reports back on Telegram. No manual steps once it is set up.

**It uses only game data (scores, quarter-by-quarter points, top scorer stat lines). It does not download or reuse any NBA broadcast footage, highlights, photos or logos.** The visuals are cards drawn from the numbers.

## What it does

Each run:

1. **Checks whether the US game day is finished.** If games are still being played it exits quietly and tries again at the next scheduled run.
2. **Fetches the data** (`fetch_games.py`): final scores and quarter scores, the top scorer of every game, and picks up to 4 featured games (closest/overtime game, biggest comeback, biggest scoring nights).
3. **Writes one script per game** (`write_script.py`) with Gemini, always as 3 parts: top scorer hook, how the game flowed, final score.
4. **Generates the voiceover** (`narrate.py`) with edge-tts, one audio file per part.
5. **Draws the cards** (`fetch_visuals.py`): final score, top scorer, quarter-by-quarter table, in the home team's colors.
6. **Renders the video** (`make_video.py`) with MoviePy. Each card is shown exactly while its part of the script is spoken. Captions follow the voiceover.
7. **Fact-checks the script** (`fact_check.py`): every number in the script must be traceable to the game data, otherwise that video is held back.
8. **Uploads to YouTube** (`upload_youtube.py`) and sends a **Telegram** summary (`notify.py`). Failures are reported on Telegram too.

`main.py` runs all of this in order and stops on the first failure.

## Requirements

- Windows (the caption font path in `make_video.py` is `C:/Windows/Fonts`; change `FONTS_DIR` for other systems)
- Python 3.10+
- Free accounts / keys:
  - [balldontlie](https://app.balldontlie.io) API key (free tier is enough: only `/games` is used)
  - [Google AI Studio](https://aistudio.google.com/apikey) Gemini API key (free tier)
  - A Google Cloud project with **YouTube Data API v3** enabled and an OAuth client of type **Desktop app**
  - A YouTube channel on the account you upload with
  - A Telegram bot from [@BotFather](https://t.me/BotFather) (optional, for notifications)

Player stats come from [`nba_api`](https://github.com/swar/nba_api), an unofficial wrapper around NBA.com. It needs no key but **NBA.com blocks most cloud/datacenter IPs**, so run this from a home connection.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`:

```
BALLDONTLIE_API_KEY=
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`TELEGRAM_CHAT_ID` is filled in automatically: open your bot in Telegram, press Start, send it a message, then run `python notify.py "hello"`.

**YouTube access:** download the OAuth client JSON from Google Cloud, rename it `client_secret.json` and put it in the project folder. While the app is in "Testing" mode, add your Google account under *Audience > Test users*. The first `python upload_youtube.py` opens a browser to authorize once and saves `token.json`.

Optional: put your own picture at `assets/avatar.png`. It is cropped to a circle and shown in the bottom-left corner of every video.

## Usage

```bash
python main.py              # whole pipeline, uploads publicly
python main.py --no-upload  # make the videos but do not upload
```

Each step can also be run on its own (`python fetch_games.py`, `python write_script.py`, ...). Output goes to `output/<US game date>/shorts/<NN_game>/`, and `output/pipeline.log` keeps the run history.

## Run it every day

Create a Windows Task Scheduler task that runs `.venv\Scripts\python.exe main.py` in the project folder, starting around 12:00 Malaysia time (UTC+8) and repeating every 30 minutes for 4 hours, with "wake the computer to run this task" on and "do not start a new instance" for overlapping runs. Every run is a cheap check until the day's games are all final, then it does the full pipeline once and skips the day afterwards. Adjust the times for your own time zone: NBA games finish roughly 13:00-14:00 UTC+8.

## Project layout

```
main.py            runs all steps, retries once if the fact check holds a video back
common.py          shared helpers: finding the latest report, per-game folders, titles, descriptions
fetch_games.py     game data, quarter scores, top scorers, featured game selection
write_script.py    Gemini script generation (3 parts per game)
narrate.py         edge-tts voiceover per part
fetch_visuals.py   Pillow cards in team colors
make_video.py      MoviePy rendering, captions, avatar
fact_check.py      verifies numbers in each script against the data
upload_youtube.py  YouTube Data API upload
notify.py          Telegram notifications
```

## Notes and limitations

- Videos and descriptions state that the commentary and visuals are AI-generated from public game data.
- `nba_api` is unofficial and its older endpoints are being deprecated; if player stats stop loading, the top-scorer cards will be missing until the code is moved to the newer endpoints.
- The fact check compares numbers of 5 and above. It does not judge wording.
- Gemini's free tier is sometimes overloaded; the script generator retries automatically.
- Keep `.env`, `client_secret.json` and `token.json` private. They are listed in `.gitignore`.

## Disclaimer

This project is not affiliated with or endorsed by the NBA or any team. Team names are used only to describe game results.
