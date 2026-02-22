from __future__ import annotations

import os


def get_bot_lang() -> str:
    raw = os.getenv("BOT_LANG", "pl").strip().lower()
    if raw in {"en", "eng", "english"}:
        return "en"
    return "pl"


def tr(*, pl: str, en: str) -> str:
    return en if get_bot_lang() == "en" else pl
