from __future__ import annotations

import requests
from django.conf import settings

TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_MESSAGE_LIMIT = 3500


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and settings.ENABLE_TELEGRAM_ALERTS)

    def send_message(self, text: str) -> None:
        if not self.is_configured():
            raise RuntimeError("Telegram bot token/chat ID is not configured.")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        for chunk in chunk_message(text):
            response = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            response.raise_for_status()


def chunk_message(text: str, limit: int = SAFE_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for section in text.split("\n\n"):
        candidate = section if not current else f"{current}\n\n{section}"
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
        current = ""
        if len(section) <= limit:
            current = section
            continue

        chunks.extend(_split_long_section(section, limit=limit))

    if current:
        chunks.append(current)
    return chunks


def _split_long_section(section: str, limit: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in section.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks
