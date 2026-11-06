import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

ENV_PATH = Path(__file__).parent / ".env"
API_URL = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LENGTH = 4000

load_dotenv(ENV_PATH)


def find_chat_id(token):
    response = requests.get(API_URL.format(token=token, method="getUpdates"), timeout=15).json()
    for update in reversed(response.get("result", [])):
        message = update.get("message")
        if message:
            return str(message["chat"]["id"])
    return None


def send_message(text):
    """Sends a Telegram message. Never raises: a failed notification must not break the pipeline."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return False

    try:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            chat_id = find_chat_id(token)
            if not chat_id:
                print("Telegram: no chat found yet. Open your bot, press Start and send it a message.")
                return False
            set_key(str(ENV_PATH), "TELEGRAM_CHAT_ID", chat_id)
            os.environ["TELEGRAM_CHAT_ID"] = chat_id

        response = requests.post(
            API_URL.format(token=token, method="sendMessage"),
            data={"chat_id": chat_id, "text": text[:MAX_MESSAGE_LENGTH], "disable_web_page_preview": "true"},
            timeout=15,
        )
        return response.ok
    except requests.RequestException as exc:
        print(f"Telegram notification failed: {exc}")
        return False


if __name__ == "__main__":
    message = " ".join(sys.argv[1:]) or "Test message from your NBA bot."
    print("Sent." if send_message(message) else "Not sent.")
