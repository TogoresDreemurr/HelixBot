import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from plugin_manager.manager import PluginManager


class DummyAuthor:
    bot = False


class DummyChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str) -> None:
        self.sent.append(content)


class DummyMessage:
    def __init__(self, content: str, channel: DummyChannel) -> None:
        self.content = content
        self.channel = channel
        self.author = DummyAuthor()


async def main() -> int:
    mgr = PluginManager(plugins_dir=ROOT_DIR / "plugins", data_dir=ROOT_DIR / "data")

    ok, msg = mgr.load("smoke")
    if not ok:
        print(f"FAIL (load 1): {msg}")
        return 1

    await mgr.dispatch_event("ping")
    handle = mgr.active.get("smoke")
    if handle is None:
        print("FAIL (missing handle after load)")
        return 1

    first_instance = handle.instance
    count_after_first = getattr(first_instance, "ping_count", None)
    if count_after_first != 1:
        print(f"FAIL (first ping): expected 1, actual {count_after_first}")
        return 1

    ok, msg = mgr.unload("smoke")
    if not ok:
        print(f"FAIL (unload): {msg}")
        return 1

    await mgr.dispatch_event("ping")
    old_count_after_unload = getattr(first_instance, "ping_count", None)
    if old_count_after_unload != 1:
        print(f"FAIL (ping after unload): expected 1, actual {old_count_after_unload}")
        return 1

    ok, msg = mgr.load("smoke")
    if not ok:
        print(f"FAIL (load 2): {msg}")
        return 1

    handle = mgr.active.get("smoke")
    if handle is None:
        print("FAIL (missing handle after reload)")
        return 1

    await mgr.dispatch_event("ping")
    count_after_reload = getattr(handle.instance, "ping_count", None)
    if count_after_reload != 1:
        print(f"FAIL (second load ping): expected 1, actual {count_after_reload}")
        return 1

    channel = DummyChannel()
    await mgr.dispatch_event("message", DummyMessage("!ping", channel))
    if len(channel.sent) != 1:
        print(f"FAIL (message duplication): expected 1, actual {len(channel.sent)}")
        return 1
    if channel.sent[0] != "pong":
        print(f"FAIL (message payload): expected pong, actual {channel.sent[0]}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
