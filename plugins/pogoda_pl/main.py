from __future__ import annotations

import asyncio
import json
import time
import unicodedata
import urllib.parse
import urllib.request

from core.i18n import get_bot_lang, tr

CITIES = {
    "warszawa": ("Warszawa", 52.2297, 21.0122),
    "krakow": ("Krakow", 50.0647, 19.9450),
    "lodz": ("Lodz", 51.7592, 19.4550),
    "wroclaw": ("Wroclaw", 51.1079, 17.0385),
    "poznan": ("Poznan", 52.4064, 16.9252),
    "gdansk": ("Gdansk", 54.3520, 18.6466),
    "szczecin": ("Szczecin", 53.4285, 14.5528),
    "bydgoszcz": ("Bydgoszcz", 53.1235, 18.0084),
    "lublin": ("Lublin", 51.2465, 22.5684),
    "bialystok": ("Bialystok", 53.1325, 23.1688),
}

WEATHER_CODE_MAP = {
    0: "bezchmurnie",
    1: "glownie bezchmurnie",
    2: "czesciowe zachmurzenie",
    3: "zachmurzenie",
    45: "mgla",
    48: "szadz/mgla osadzajaca",
    51: "lekka mzawka",
    53: "umiarkowana mzawka",
    55: "intensywna mzawka",
    61: "lekki deszcz",
    63: "umiarkowany deszcz",
    65: "silny deszcz",
    71: "lekki snieg",
    73: "umiarkowany snieg",
    75: "silny snieg",
    80: "przelotny lekki deszcz",
    81: "przelotny umiarkowany deszcz",
    82: "przelotny silny deszcz",
    95: "burza",
}

WEATHER_CODE_MAP_EN = {
    0: "clear sky",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
}

CACHE_TTL_SECONDS = 300


class Plugin:
    def __init__(self) -> None:
        self._api = None
        self._cache: dict[str, tuple[float, dict]] = {}

    def on_load(self, api) -> None:
        self._api = api
        api.register_event("message", self.on_message)
        api.logger("[pogoda_pl] loaded: !pogoda [miasto|all|help]")

    async def on_message(self, message) -> None:
        content = (message.content or "").strip()
        if not content.startswith("!pogoda"):
            return

        raw_arg = content[7:].strip()
        if not raw_arg:
            await self._send_all(message)
            return

        arg = self._normalize_city(raw_arg)
        if arg in {"help", "pomoc"}:
            await message.channel.send(self._help_text())
            return
        if arg in {"all", "wszystkie"}:
            await self._send_all(message)
            return
        if arg not in CITIES:
            city_list = ", ".join(city for city, _, _ in CITIES.values())
            await message.channel.send(
                tr(
                    pl="Nieznane miasto. Uzyj: `!pogoda <miasto>` lub `!pogoda all`.\n"
                    f"Obslugiwane miasta: {city_list}",
                    en="Unknown city. Use: `!pogoda <city>` or `!pogoda all`.\n"
                    f"Supported cities: {city_list}",
                )
            )
            return

        report = await self._city_report(arg)
        await message.channel.send(report)

    @staticmethod
    def _normalize_city(raw: str) -> str:
        lowered = raw.strip().lower()
        normalized = unicodedata.normalize("NFD", lowered)
        no_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return no_accents.replace("-", " ").replace("  ", " ").strip().replace(" ", "")

    def _help_text(self) -> str:
        city_list = ", ".join(city for city, _, _ in CITIES.values())
        return tr(
            pl=(
                "Komendy pogodowe:\n"
                "`!pogoda` - pogoda dla najwiekszych miast w Polsce\n"
                "`!pogoda <miasto>` - szczegoly dla jednego miasta\n"
                "`!pogoda all` - to samo co `!pogoda`\n"
                "`!pogoda help` - pomoc\n"
                f"Miasta: {city_list}"
            ),
            en=(
                "Weather commands:\n"
                "`!pogoda` - weather for major cities in Poland\n"
                "`!pogoda <city>` - details for one city\n"
                "`!pogoda all` - same as `!pogoda`\n"
                "`!pogoda help` - help\n"
                f"Cities: {city_list}"
            ),
        )

    async def _send_all(self, message) -> None:
        lines = []
        for key in CITIES:
            lines.append(await self._city_report(key, compact=True))
        await message.channel.send(
            tr(
                pl="Pogoda - najwieksze miasta w Polsce:\n",
                en="Weather - major cities in Poland:\n",
            )
            + "\n".join(lines)
        )

    async def _city_report(self, city_key: str, *, compact: bool = False) -> str:
        city_name, _, _ = CITIES[city_key]
        try:
            data = await self._fetch_city_weather(city_key)
        except Exception:
            return tr(
                pl=f"{city_name}: blad pobierania danych pogodowych.",
                en=f"{city_name}: error fetching weather data.",
            )

        desc_map = WEATHER_CODE_MAP_EN if get_bot_lang() == "en" else WEATHER_CODE_MAP
        fallback = "conditions unknown" if get_bot_lang() == "en" else "warunki nieokreslone"
        desc = desc_map.get(data["weather_code"], fallback)
        temp = data["temperature_2m"]
        feels = data["apparent_temperature"]
        humidity = data["relative_humidity_2m"]
        wind = data["wind_speed_10m"]

        if compact:
            return tr(
                pl=f"{city_name}: {temp}C (odcz. {feels}C), {desc}, wiatr {wind} km/h",
                en=f"{city_name}: {temp}C (feels {feels}C), {desc}, wind {wind} km/h",
            )
        return tr(
            pl=f"Pogoda dla {city_name}: {temp}C (odczuwalna {feels}C), "
            f"wilgotnosc {humidity}%, wiatr {wind} km/h, warunki: {desc}",
            en=f"Weather for {city_name}: {temp}C (feels {feels}C), "
            f"humidity {humidity}%, wind {wind} km/h, conditions: {desc}",
        )

    async def _fetch_city_weather(self, city_key: str) -> dict:
        now = time.time()
        cached = self._cache.get(city_key)
        if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]

        _, lat, lon = CITIES[city_key]
        data = await asyncio.to_thread(self._http_fetch, lat, lon)
        self._cache[city_key] = (now, data)
        return data

    @staticmethod
    def _http_fetch(latitude: float, longitude: float) -> dict:
        base = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "Europe/Warsaw",
            "forecast_days": "1",
        }
        url = f"{base}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "HelixBot-PogodaPL/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))

        current = payload.get("current")
        if not isinstance(current, dict):
            raise ValueError("Malformed weather payload")
        required = {
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "weather_code",
            "wind_speed_10m",
        }
        if not required.issubset(set(current.keys())):
            raise ValueError("Incomplete weather payload")
        return current
