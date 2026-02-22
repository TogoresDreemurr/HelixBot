from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

from core.i18n import tr


NBP_GOLD_URL = "https://api.nbp.pl/api/cenyzlota?format=json"
STOOQ_XAUUSD_URL = "https://stooq.pl/q/l/?s=xauusd&i=d&f=sd2t2ohlcv&h&e=csv"
GOLDAPI_XAUUSD_URL = "https://www.goldapi.io/api/XAU/USD"

SOURCE_NBP = "nbp"
SOURCE_STOOQ = "stooq"
SOURCE_GOLDAPI = "goldapi"
SOURCE_XTB = "xtb"
AVAILABLE_SOURCES = (SOURCE_NBP, SOURCE_STOOQ, SOURCE_GOLDAPI, SOURCE_XTB)
DEFAULT_SOURCE = SOURCE_NBP

DEFAULT_INTERVAL_SECONDS = 1800
MIN_INTERVAL_SECONDS = 2
MAX_INTERVAL_SECONDS = 86400


class Plugin:
    def __init__(self) -> None:
        self._api = None
        self._state_path: Path | None = None
        self._task: asyncio.Task | None = None
        self._state: dict = {
            "enabled": False,
            "channel_id": None,
            "interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "source": DEFAULT_SOURCE,
        }

    def on_load(self, api) -> None:
        self._api = api
        self._state_path = api.get_data_path() / "state.json"
        self._load_state()
        api.register_event("message", self.on_message)
        api.logger("[gold_pln] loaded: !zloto start|stop|status|now|source")
        if self._state.get("enabled"):
            self._ensure_task()

    def on_disable(self) -> None:
        self._cancel_task()
        self._save_state()

    def on_unload(self) -> None:
        self._cancel_task()
        self._save_state()

    async def on_message(self, message) -> None:
        if self._state.get("enabled"):
            self._ensure_task()

        content = (message.content or "").strip()
        if not content.startswith("!zloto"):
            return

        raw = content[6:].strip()
        if not raw:
            await message.channel.send(self._help_text())
            return

        parts = raw.split()
        sub = parts[0].lower()
        rest = parts[1:]

        if sub == "start":
            await self._cmd_start(message, rest)
            return
        if sub == "stop":
            await self._cmd_stop(message)
            return
        if sub == "status":
            await self._cmd_status(message)
            return
        if sub == "now":
            await self._cmd_now(message)
            return
        if sub == "source":
            await self._cmd_source(message, rest)
            return
        if sub == "help":
            await message.channel.send(self._help_text())
            return

        await message.channel.send(
            tr(
                pl="Nieznana komenda. Uzyj `!zloto help`.",
                en="Unknown command. Use `!zloto help`.",
            )
        )

    async def _cmd_start(self, message, args: list[str]) -> None:
        interval_seconds = self._state.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
        if args:
            parsed = self._parse_interval_seconds(args[0])
            if parsed is None:
                await message.channel.send(
                    tr(
                        pl="Podaj interwal: `2s..86400s` albo `1m..1440m`, np. `!zloto start 2s` lub `!zloto start 15m`.",
                        en="Provide interval: `2s..86400s` or `1m..1440m`, e.g. `!zloto start 2s` or `!zloto start 15m`.",
                    )
                )
                return
            interval_seconds = parsed

        self._state["enabled"] = True
        self._state["channel_id"] = message.channel.id
        self._state["interval_seconds"] = int(interval_seconds)
        self._save_state()
        self._ensure_task()

        await message.channel.send(
            tr(
                pl=f"Start monitoringu zlota: kanal <#{message.channel.id}>, co {self._format_interval(int(interval_seconds))}.",
                en=f"Gold monitor started: channel <#{message.channel.id}>, every {self._format_interval(int(interval_seconds))}.",
            )
        )
        await self._post_once(reason="manual")

    async def _cmd_stop(self, message) -> None:
        was_enabled = bool(self._state.get("enabled"))
        self._state["enabled"] = False
        self._save_state()
        self._cancel_task()
        if was_enabled:
            await message.channel.send(tr(pl="Monitoring zlota zatrzymany.", en="Gold monitor stopped."))
        else:
            await message.channel.send(
                tr(pl="Monitoring juz byl zatrzymany.", en="Gold monitor was already stopped.")
            )

    async def _cmd_status(self, message) -> None:
        enabled = bool(self._state.get("enabled"))
        channel_id = self._state.get("channel_id")
        interval_seconds = int(self._state.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
        source = str(self._state.get("source", DEFAULT_SOURCE))
        task_running = self._task is not None and not self._task.done()
        await message.channel.send(
            tr(
                pl=(
                    "Status monitoringu zlota:\n"
                    f"enabled={enabled}\n"
                    f"channel_id={channel_id}\n"
                    f"source={source}\n"
                    f"interval={self._format_interval(interval_seconds)} ({interval_seconds}s)\n"
                    f"loop_running={task_running}"
                ),
                en=(
                    "Gold monitor status:\n"
                    f"enabled={enabled}\n"
                    f"channel_id={channel_id}\n"
                    f"source={source}\n"
                    f"interval={self._format_interval(interval_seconds)} ({interval_seconds}s)\n"
                    f"loop_running={task_running}"
                ),
            )
        )

    async def _cmd_now(self, message) -> None:
        text = await self._format_price_message(reason="manual")
        await message.channel.send(text)

    async def _cmd_source(self, message, args: list[str]) -> None:
        if not args:
            source = str(self._state.get("source", DEFAULT_SOURCE))
            await message.channel.send(
                tr(
                    pl=f"Aktywne zrodlo: `{source}`. Uzyj `!zloto source list` lub `!zloto source set <nazwa>`.",
                    en=f"Active source: `{source}`. Use `!zloto source list` or `!zloto source set <name>`.",
                )
            )
            return

        sub = args[0].lower()
        if sub == "list":
            await message.channel.send(
                tr(pl="Dostepne zrodla: ", en="Available sources: ") + ", ".join(AVAILABLE_SOURCES)
            )
            return

        if sub == "set":
            if len(args) < 2:
                await message.channel.send(
                    tr(
                        pl="Uzyj: `!zloto source set <nbp|stooq|goldapi>`.",
                        en="Use: `!zloto source set <nbp|stooq|goldapi|xtb>`.",
                    )
                )
                return
            source = args[1].strip().lower()
            if source not in AVAILABLE_SOURCES:
                await message.channel.send(
                    tr(pl="Nieznane zrodlo. Dostepne: ", en="Unknown source. Available: ")
                    + ", ".join(AVAILABLE_SOURCES)
                )
                return
            self._state["source"] = source
            self._save_state()
            await message.channel.send(
                tr(pl=f"Ustawiono zrodlo na `{source}`.", en=f"Source set to `{source}`.")
            )
            return

        await message.channel.send(
            tr(
                pl="Nieznana komenda source. Uzyj: `!zloto source`, `!zloto source list`, `!zloto source set <nazwa>`.",
                en="Unknown source command. Use: `!zloto source`, `!zloto source list`, `!zloto source set <name>`.",
            )
        )

    def _ensure_task(self) -> None:
        if not self._state.get("enabled"):
            return
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._task = loop.create_task(self._publisher_loop())

    def _cancel_task(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _publisher_loop(self) -> None:
        try:
            bot = self._api.bot if self._api else None
            if bot is None:
                return
            await bot.wait_until_ready()
            while self._state.get("enabled"):
                await self._post_once(reason="routine")
                interval_seconds = int(self._state.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
                await asyncio.sleep(max(MIN_INTERVAL_SECONDS, interval_seconds))
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if self._api:
                self._api.logger(f"[gold_pln] loop crashed: {exc}")
        finally:
            self._task = None

    async def _post_once(self, *, reason: str) -> None:
        channel_id = self._state.get("channel_id")
        if not channel_id:
            if self._api:
                self._api.logger("[gold_pln] missing channel_id, skipping publish")
            return
        channel = await self._resolve_channel(int(channel_id))
        if channel is None:
            if self._api:
                self._api.logger(f"[gold_pln] channel not found: {channel_id}")
            return
        text = await self._format_price_message(reason=reason)
        await channel.send(text)

    async def _format_price_message(self, *, reason: str) -> str:
        source = str(self._state.get("source", DEFAULT_SOURCE))
        try:
            payload = await asyncio.to_thread(self._fetch_gold_price, source)
            price = payload["price"]
            unit = payload["unit"]
            label = payload["label"]
            day = payload["source_time"]
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            return (
                tr(
                    pl=f"Zloto ({label}): {price} {unit} (czas zrodla: {day}). Aktualizacja: {stamp}. [{reason}]",
                    en=f"Gold ({label}): {price} {unit} (source time: {day}). Updated: {stamp}. [{reason}]",
                )
            )
        except Exception as exc:
            if self._api:
                self._api.logger(f"[gold_pln] fetch error: {exc}")
            return tr(
                pl=f"Zloto: blad pobierania danych ze zrodla `{source}`.",
                en=f"Gold: failed to fetch data from source `{source}`.",
            )

    @staticmethod
    def _fetch_gold_price(source: str) -> dict:
        source = source.strip().lower()
        if source == SOURCE_NBP:
            return Plugin._fetch_gold_price_nbp()
        if source == SOURCE_STOOQ:
            return Plugin._fetch_gold_price_stooq()
        if source == SOURCE_GOLDAPI:
            return Plugin._fetch_gold_price_goldapi()
        if source == SOURCE_XTB:
            return Plugin._fetch_gold_price_xtb()
        raise ValueError(f"Unsupported source: {source}")

    @staticmethod
    def _fetch_gold_price_nbp() -> dict:
        req = urllib.request.Request(
            NBP_GOLD_URL,
            headers={
                "User-Agent": "HelixBot-GoldPLN/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list) or not payload:
            raise ValueError("Malformed NBP payload")
        row = payload[0]
        if not isinstance(row, dict):
            raise ValueError("Malformed NBP row")
        if "cena" not in row or "data" not in row:
            raise ValueError("Incomplete NBP row")
        return {
            "price": row["cena"],
            "unit": "PLN/g",
            "label": "NBP",
            "source_time": row["data"],
        }

    @staticmethod
    def _fetch_gold_price_stooq() -> dict:
        req = urllib.request.Request(
            STOOQ_XAUUSD_URL,
            headers={
                "User-Agent": "HelixBot-GoldPLN/1.0",
                "Accept": "text/plain",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            text = response.read().decode("utf-8", errors="replace")

        parsed = Plugin._parse_stooq_payload(text)
        if parsed is None:
            snippet = text.strip().replace("\n", " ")[:120]
            raise ValueError(f"Malformed Stooq payload: {snippet!r}")
        return parsed

    @staticmethod
    def _parse_stooq_payload(text: str) -> dict | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1) Typical CSV/semicolon responses (with or without header)
        for line in lines:
            lower = line.lower()
            if "symbol" in lower and ("date" in lower or "czas" in lower):
                continue
            row = Plugin._split_csv_like(line)
            if len(row) < 2:
                continue
            price = Plugin._pick_price_from_fields(row)
            if price is None:
                continue
            source_time = Plugin._pick_time_from_fields(row)
            return {
                "price": price,
                "unit": "USD/oz",
                "label": "Stooq XAUUSD",
                "source_time": source_time or "n/a",
            }

        # 2) Sometimes websites return HTML/error pages; try a loose fallback
        html_price = Plugin._find_number_like_price(text)
        if html_price is not None:
            return {
                "price": html_price,
                "unit": "USD/oz",
                "label": "Stooq XAUUSD",
                "source_time": "n/a",
            }
        return None

    @staticmethod
    def _split_csv_like(line: str) -> list[str]:
        if line.count(";") > line.count(","):
            return [part.strip() for part in line.split(";")]
        return [part.strip() for part in line.split(",")]

    @staticmethod
    def _pick_price_from_fields(fields: list[str]) -> str | None:
        # Prefer close/last style columns (usually near row end), fallback to first valid number.
        for field in reversed(fields):
            value = Plugin._normalize_numeric(field)
            if value is not None:
                return value
        return None

    @staticmethod
    def _pick_time_from_fields(fields: list[str]) -> str | None:
        # Detect patterns like YYYY-MM-DD and HH:MM[:SS]
        date_part = None
        time_part = None
        for field in fields:
            s = field.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                date_part = s
            elif re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", s):
                time_part = s
        if date_part and time_part:
            return f"{date_part} {time_part}"
        if date_part:
            return date_part
        return None

    @staticmethod
    def _normalize_numeric(raw: str) -> str | None:
        s = raw.strip().replace(" ", "")
        if not s or s.lower() in {"n/a", "-", "null"}:
            return None
        # Handle thousands separators and decimal comma
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            value = float(s)
        except ValueError:
            return None
        if value <= 0:
            return None
        return str(value)

    @staticmethod
    def _find_number_like_price(text: str) -> str | None:
        # Last resort for non-CSV payloads.
        candidates = re.findall(r"\b\d{3,5}(?:[.,]\d{1,4})?\b", text)
        if not candidates:
            return None
        for raw in reversed(candidates):
            parsed = Plugin._normalize_numeric(raw)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _fetch_gold_price_goldapi() -> dict:
        api_key = os.getenv("GOLDAPI_KEY", "").strip()
        if not api_key:
            raise ValueError("GOLDAPI_KEY is not set")

        req = urllib.request.Request(
            GOLDAPI_XAUUSD_URL,
            headers={
                "x-access-token": api_key,
                "User-Agent": "HelixBot-GoldPLN/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, dict):
            raise ValueError("Malformed GoldAPI payload")
        if "price" not in payload:
            raise ValueError("GoldAPI payload has no price")

        source_time = str(payload.get("timestamp", "n/a"))
        return {
            "price": payload["price"],
            "unit": "USD/oz",
            "label": "GoldAPI XAUUSD",
            "source_time": source_time,
        }

    @staticmethod
    def _fetch_gold_price_xtb() -> dict:
        host = os.getenv("XTB_API_HOST", "xapi.xtb.com").strip() or "xapi.xtb.com"
        port_raw = os.getenv("XTB_API_PORT", "5124").strip() or "5124"
        user_id = os.getenv("XTB_USER_ID", "").strip()
        password = os.getenv("XTB_PASSWORD", "").strip()
        symbol = os.getenv("XTB_SYMBOL", "GOLD").strip() or "GOLD"

        if not user_id or not password:
            raise ValueError("XTB_USER_ID / XTB_PASSWORD are not set")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("XTB_API_PORT must be integer") from exc

        timeout = 10
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            context = ssl.create_default_context()
            with context.wrap_socket(sock, server_hostname=host) as conn:
                login = Plugin._xtb_send_command(
                    conn,
                    {
                        "command": "login",
                        "arguments": {"userId": user_id, "password": password},
                    },
                )
                if not login.get("status"):
                    err = login.get("errorDescr", "login failed")
                    raise ValueError(f"XTB login failed: {err}")

                try:
                    quote = Plugin._xtb_send_command(
                        conn,
                        {
                            "command": "getSymbol",
                            "arguments": {"symbol": symbol},
                        },
                    )
                    if not quote.get("status"):
                        err = quote.get("errorDescr", "getSymbol failed")
                        raise ValueError(f"XTB getSymbol failed: {err}")
                    data = quote.get("returnData")
                    if not isinstance(data, dict):
                        raise ValueError("XTB malformed quote payload")

                    ask = data.get("ask")
                    bid = data.get("bid")
                    if ask is None and bid is None:
                        raise ValueError("XTB quote has no bid/ask")

                    price = ask if ask is not None else bid
                    raw_time = data.get("time")
                    source_time = "n/a"
                    if isinstance(raw_time, (int, float)):
                        source_time = datetime.fromtimestamp(
                            float(raw_time) / 1000.0, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S UTC")

                    return {
                        "price": price,
                        "unit": "USD/oz",
                        "label": f"XTB {symbol}",
                        "source_time": source_time,
                    }
                finally:
                    try:
                        Plugin._xtb_send_command(conn, {"command": "logout"})
                    except Exception:
                        pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def _xtb_send_command(conn: ssl.SSLSocket, payload: dict) -> dict:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        conn.sendall(raw + b"\n")

        decoder = json.JSONDecoder()
        buffer = ""
        conn.settimeout(10)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                raise ValueError("XTB connection closed")
            buffer += chunk.decode("utf-8", errors="replace")
            stripped = buffer.lstrip()
            try:
                result, _ = decoder.raw_decode(stripped)
                if not isinstance(result, dict):
                    raise ValueError("XTB non-object response")
                return result
            except json.JSONDecodeError:
                continue

    async def _resolve_channel(self, channel_id: int):
        bot = self._api.bot if self._api else None
        if bot is None:
            return None
        channel = bot.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await bot.fetch_channel(channel_id)
        except Exception:
            return None

    def _load_state(self) -> None:
        if self._state_path is None:
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            enabled = bool(raw.get("enabled", False))
            channel_id = raw.get("channel_id")
            interval_seconds = raw.get("interval_seconds")
            interval_minutes_legacy = raw.get("interval_minutes")
            if channel_id is not None:
                try:
                    channel_id = int(channel_id)
                except (TypeError, ValueError):
                    channel_id = None
            if interval_seconds is not None:
                parsed_interval_seconds = self._parse_interval_seconds(str(interval_seconds))
            else:
                parsed_interval_seconds = None

            if parsed_interval_seconds is None and interval_minutes_legacy is not None:
                parsed_minutes = self._parse_interval_seconds(f"{interval_minutes_legacy}m")
                parsed_interval_seconds = parsed_minutes

            if parsed_interval_seconds is None:
                parsed_interval_seconds = DEFAULT_INTERVAL_SECONDS

            source = str(raw.get("source", DEFAULT_SOURCE)).strip().lower()
            if source not in AVAILABLE_SOURCES:
                source = DEFAULT_SOURCE

            self._state = {
                "enabled": enabled,
                "channel_id": channel_id,
                "interval_seconds": parsed_interval_seconds,
                "source": source,
            }
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        try:
            self._state_path.write_text(
                json.dumps(self._state, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError as exc:
            if self._api:
                self._api.logger(f"[gold_pln] state save failed: {exc}")

    @staticmethod
    def _parse_interval_seconds(raw: str) -> int | None:
        raw = raw.strip()
        if not raw:
            return None

        if raw[-1].lower() in {"s", "m"}:
            unit = raw[-1].lower()
            number = raw[:-1].strip()
        else:
            unit = "m"
            number = raw

        if not number.isdigit():
            return None
        value = int(number)
        if unit == "m":
            value *= 60

        if value < MIN_INTERVAL_SECONDS or value > MAX_INTERVAL_SECONDS:
            return None
        return value

    @staticmethod
    def _format_interval(seconds: int) -> str:
        if seconds % 60 == 0:
            return f"{seconds // 60}m"
        return f"{seconds}s"

    @staticmethod
    def _help_text() -> str:
        return tr(
            pl=(
                "Komendy zlota:\n"
                "`!zloto start [interwal]` - uruchom monitor (np. `2s`, `15m`, domyslnie 30m)\n"
                "`!zloto stop` - zatrzymaj monitor\n"
                "`!zloto status` - pokaz status\n"
                "`!zloto now` - pokaz cene teraz\n"
                "`!zloto source` - pokaz aktywne zrodlo\n"
                "`!zloto source list` - lista zrodel\n"
                "`!zloto source set <nbp|stooq|goldapi|xtb>` - zmien zrodlo\n"
                "`!zloto help` - pomoc"
            ),
            en=(
                "Gold commands:\n"
                "`!zloto start [interval]` - start monitor (e.g. `2s`, `15m`, default 30m)\n"
                "`!zloto stop` - stop monitor\n"
                "`!zloto status` - show status\n"
                "`!zloto now` - show current price now\n"
                "`!zloto source` - show active source\n"
                "`!zloto source list` - list sources\n"
                "`!zloto source set <nbp|stooq|goldapi|xtb>` - change source\n"
                "`!zloto help` - help"
            ),
        )
