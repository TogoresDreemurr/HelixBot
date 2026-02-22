import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from plugin_manager.manager import PluginManager


class DummyAuthor:
    def __init__(self, user_id: int = 101) -> None:
        self.bot = False
        self.id = user_id


class DummyGuild:
    def __init__(self, guild_id: int = 202) -> None:
        self.id = guild_id


class DummyChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str) -> None:
        self.sent.append(content)


class DummyMessage:
    def __init__(self, content: str, channel: DummyChannel, *, user_id: int = 101) -> None:
        self.content = content
        self.channel = channel
        self.author = DummyAuthor(user_id)
        self.guild = DummyGuild()


async def main() -> int:
    mgr = PluginManager(plugins_dir=ROOT_DIR / "plugins", data_dir=ROOT_DIR / "data")
    ok, msg = mgr.load("tasker")
    if not ok:
        print(f"FAIL (load): {msg}")
        return 1

    ch = DummyChannel()
    await mgr.dispatch_event("message", DummyMessage("!task add kupic mleko", ch))
    await mgr.dispatch_event("message", DummyMessage("!task list", ch))
    await mgr.dispatch_event("message", DummyMessage("!task done 1", ch))
    await mgr.dispatch_event("message", DummyMessage("!task stats", ch))
    await mgr.dispatch_event("message", DummyMessage("!task remove 1", ch))
    await mgr.dispatch_event("message", DummyMessage("!roll 2d6+1", ch))

    checks = [
        ("Dodano zadanie #1", any("Dodano zadanie #1" in msg for msg in ch.sent)),
        ("Twoje zadania:", any("Twoje zadania:" in msg for msg in ch.sent)),
        ("Oznaczono jako wykonane", any("Oznaczono jako wykonane" in msg for msg in ch.sent)),
        ("Statystyki zadan", any("Statystyki zadan" in msg for msg in ch.sent)),
        ("Usunieto zadanie #1", any("Usunieto zadanie #1" in msg for msg in ch.sent)),
        ("Wynik `2d6+1`", any("Wynik `2d6+1`" in msg for msg in ch.sent)),
    ]
    for label, ok in checks:
        if not ok:
            print(f"FAIL (missing output): {label}")
            return 1

    ok, msg = mgr.unload("tasker")
    if not ok:
        print(f"FAIL (unload): {msg}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
