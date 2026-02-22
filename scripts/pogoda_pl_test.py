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
    ok, msg = mgr.load("pogoda_pl")
    if not ok:
        print(f"FAIL (load): {msg}")
        return 1

    handle = mgr.active.get("pogoda_pl")
    if handle is None:
        print("FAIL (missing handle)")
        return 1

    plugin = handle.instance

    async def fake_fetch(city_key: str) -> dict:
        _ = city_key
        return {
            "temperature_2m": 12.3,
            "apparent_temperature": 10.0,
            "relative_humidity_2m": 70,
            "weather_code": 2,
            "wind_speed_10m": 15.8,
        }

    plugin._fetch_city_weather = fake_fetch

    ch = DummyChannel()
    await mgr.dispatch_event("message", DummyMessage("!pogoda warszawa", ch))
    await mgr.dispatch_event("message", DummyMessage("!pogoda all", ch))
    await mgr.dispatch_event("message", DummyMessage("!pogoda help", ch))

    if not any("Pogoda dla Warszawa:" in msg for msg in ch.sent):
        print("FAIL (single city output)")
        return 1
    if not any("Pogoda - najwieksze miasta w Polsce:" in msg for msg in ch.sent):
        print("FAIL (all cities output)")
        return 1
    if not any("Komendy pogodowe:" in msg for msg in ch.sent):
        print("FAIL (help output)")
        return 1

    ok, msg = mgr.unload("pogoda_pl")
    if not ok:
        print(f"FAIL (unload): {msg}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
