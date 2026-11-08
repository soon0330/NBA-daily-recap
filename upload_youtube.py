import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import build_description, build_tags, build_title, find_latest_report, short_dirs
from fact_check import check_script

BASE_DIR = Path(__file__).parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SPORTS_CATEGORY_ID = "17"
PRIVACY_STATUS = "public"
PUBLISH_SPACING_MINUTES = 0


def get_authenticated_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                print(f"Missing {CLIENT_SECRETS_FILE.name}. Set up OAuth credentials first.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path, game, date_str, publish_at=None):
    """Uploads public right away, or private with a scheduled publish time when publish_at is given."""
    status_body = {"privacyStatus": PRIVACY_STATUS, "selfDeclaredMadeForKids": False}
    if publish_at is not None:
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": build_title(game, date_str),
            "description": build_description(game, date_str),
            "tags": build_tags(game),
            "categoryId": SPORTS_CATEGORY_ID,
        },
        "status": status_body,
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")
    return response


def main():
    day_dir, report = find_latest_report()
    if report is None:
        print("No games.json report found. Run fetch_games.py first.")
        sys.exit(1)

    pending = []
    for game, folder in short_dirs(day_dir, report):
        video_path = folder / "final_video.mp4"
        if not video_path.exists() or (folder / "uploaded.json").exists():
            continue
        pending.append((game, folder, video_path))

    if not pending:
        print("Nothing to upload (no finished videos, or all already uploaded).")
        return

    print(f"{len(pending)} video(s) to upload:")
    for game, _, _ in pending:
        print(f"  - {build_title(game, report['date'])}")

    youtube = get_authenticated_service()

    release_slot = 0
    for game, folder, video_path in pending:
        problems = check_script(game, (folder / "script.txt").read_text(encoding="utf-8"))
        blocked_marker = folder / "blocked.json"
        if problems:
            print(f"\nBLOCKED {game['matchup']}: numbers in the script not found in the game data: {problems}")
            blocked_marker.write_text(json.dumps({"unverified_numbers": problems}), encoding="utf-8")
            continue
        blocked_marker.unlink(missing_ok=True)

        publish_at = None
        if PUBLISH_SPACING_MINUTES > 0 and release_slot > 0:
            publish_at = datetime.now(timezone.utc) + timedelta(minutes=PUBLISH_SPACING_MINUTES * release_slot)
        release_slot += 1

        print(f"\nUploading {game['matchup']}...")
        response = upload_video(youtube, video_path, game, report["date"], publish_at)
        video_id = response["id"]
        record = {"video_id": video_id, "publish_at": publish_at.isoformat() if publish_at else None}
        (folder / "uploaded.json").write_text(json.dumps(record), encoding="utf-8")
        when = f"scheduled for {publish_at.astimezone():%H:%M}" if publish_at else "public now"
        print(f"Uploaded ({when}): https://www.youtube.com/watch?v={video_id}")

    print("\nAll videos uploaded.")


if __name__ == "__main__":
    main()
