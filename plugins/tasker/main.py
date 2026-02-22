from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from core.i18n import tr


ROLL_RE = re.compile(r"^(?:(\d{1,2})d)?(\d{1,4})([+-]\d{1,4})?$")
MAX_DICE = 20
MAX_SIDES = 1000
MAX_TASKS_PER_USER = 100


class Plugin:
    def __init__(self) -> None:
        self._api = None
        self._state_path: Path | None = None
        self._state: dict = {"tasks": {}}

    def on_load(self, api) -> None:
        self._api = api
        self._state_path = api.get_data_path() / "state.json"
        self._load_state()
        api.register_event("message", self.on_message)
        api.logger("[tasker] loaded: !task (add/list/done/remove/help/stats), !roll")

    def on_unload(self) -> None:
        self._save_state()

    def on_disable(self) -> None:
        self._save_state()

    def _load_state(self) -> None:
        if self._state_path is None:
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("tasks"), dict):
                self._state = raw
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._state = {"tasks": {}}

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
                self._api.logger(f"[tasker] state save failed: {exc}")

    @staticmethod
    def _scope_key(message) -> str:
        guild_id = message.guild.id if message.guild else "dm"
        return f"{guild_id}:{message.author.id}"

    def _user_tasks(self, message) -> list[dict]:
        key = self._scope_key(message)
        tasks = self._state.setdefault("tasks", {}).setdefault(key, [])
        if not isinstance(tasks, list):
            tasks = []
            self._state["tasks"][key] = tasks
        return tasks

    async def on_message(self, message) -> None:
        content = (message.content or "").strip()
        if not content:
            return

        if content.startswith("!roll"):
            arg = content[5:].strip() or "1d6"
            await self._handle_roll(message, arg)
            return

        if not content.startswith("!task"):
            return

        raw = content[5:].strip()
        if not raw:
            await message.channel.send(self._task_help())
            return

        parts = raw.split()
        sub = parts[0].lower()
        rest = raw[len(parts[0]) :].strip()

        if sub == "add":
            await self._task_add(message, rest)
            return
        if sub == "list":
            await self._task_list(message)
            return
        if sub == "done":
            await self._task_done(message, rest)
            return
        if sub == "remove":
            await self._task_remove(message, rest)
            return
        if sub == "stats":
            await self._task_stats(message)
            return
        if sub == "help":
            await message.channel.send(self._task_help())
            return

        await message.channel.send(
            tr(
                pl=f"Nieznana podkomenda `!task {sub}`. Uzyj `!task help`.",
                en=f"Unknown subcommand `!task {sub}`. Use `!task help`.",
            )
        )

    async def _handle_roll(self, message, arg: str) -> None:
        parsed = ROLL_RE.match(arg.lower())
        if not parsed:
            await message.channel.send(
                tr(
                    pl="Bledny format. Uzyj np. `!roll 1d20`, `!roll 4d6+2`, `!roll 100`.",
                    en="Invalid format. Use e.g. `!roll 1d20`, `!roll 4d6+2`, `!roll 100`.",
                )
            )
            return

        dice_count = int(parsed.group(1) or "1")
        sides = int(parsed.group(2))
        modifier = int(parsed.group(3) or "0")

        if dice_count < 1 or dice_count > MAX_DICE:
            await message.channel.send(
                tr(
                    pl=f"Liczba kostek musi byc w zakresie 1-{MAX_DICE}.",
                    en=f"Dice count must be in range 1-{MAX_DICE}.",
                )
            )
            return
        if sides < 2 or sides > MAX_SIDES:
            await message.channel.send(
                tr(
                    pl=f"Liczba scian musi byc w zakresie 2-{MAX_SIDES}.",
                    en=f"Side count must be in range 2-{MAX_SIDES}.",
                )
            )
            return

        rolls = [random.randint(1, sides) for _ in range(dice_count)]
        base_total = sum(rolls)
        total = base_total + modifier
        mod_text = f"{modifier:+d}" if modifier else "+0"
        detail = ", ".join(str(x) for x in rolls)
        await message.channel.send(
            tr(
                pl=f"Wynik `{dice_count}d{sides}{mod_text}`: [{detail}] -> {base_total} {mod_text} = **{total}**",
                en=f"Result `{dice_count}d{sides}{mod_text}`: [{detail}] -> {base_total} {mod_text} = **{total}**",
            )
        )

    async def _task_add(self, message, text: str) -> None:
        title = text.strip()
        if not title:
            await message.channel.send(
                tr(
                    pl="Podaj tresc zadania: `!task add <tresc>`.",
                    en="Provide task text: `!task add <text>`.",
                )
            )
            return
        if len(title) > 180:
            await message.channel.send(
                tr(
                    pl="Zadanie jest za dlugie (max 180 znakow).",
                    en="Task is too long (max 180 chars).",
                )
            )
            return

        tasks = self._user_tasks(message)
        if len(tasks) >= MAX_TASKS_PER_USER:
            await message.channel.send(
                tr(
                    pl=f"Osiagnieto limit {MAX_TASKS_PER_USER} zadan.",
                    en=f"Reached limit of {MAX_TASKS_PER_USER} tasks.",
                )
            )
            return

        next_id = max((int(item.get("id", 0)) for item in tasks), default=0) + 1
        tasks.append(
            {
                "id": next_id,
                "title": title,
                "done": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save_state()
        await message.channel.send(
            tr(
                pl=f"Dodano zadanie #{next_id}: {title}",
                en=f"Added task #{next_id}: {title}",
            )
        )

    async def _task_list(self, message) -> None:
        tasks = self._user_tasks(message)
        if not tasks:
            await message.channel.send(
                tr(
                    pl="Brak zadan. Dodaj: `!task add <tresc>`.",
                    en="No tasks. Add one: `!task add <text>`.",
                )
            )
            return

        lines = []
        for item in tasks[:20]:
            status = "x" if item.get("done") else " "
            task_id = item.get("id")
            title = item.get("title", "")
            lines.append(f"[{status}] #{task_id} {title}")
        if len(tasks) > 20:
            lines.append(
                tr(
                    pl=f"... i jeszcze {len(tasks) - 20} pozycji",
                    en=f"... and {len(tasks) - 20} more items",
                )
            )
        await message.channel.send(
            tr(pl="Twoje zadania:\n", en="Your tasks:\n") + "\n".join(lines)
        )

    async def _task_done(self, message, raw_id: str) -> None:
        task_id = self._parse_task_id(raw_id)
        if task_id is None:
            await message.channel.send(
                tr(
                    pl="Podaj numer zadania: `!task done <id>`.",
                    en="Provide task number: `!task done <id>`.",
                )
            )
            return

        tasks = self._user_tasks(message)
        for item in tasks:
            if item.get("id") == task_id:
                if item.get("done"):
                    await message.channel.send(
                        tr(
                            pl=f"Zadanie #{task_id} jest juz oznaczone jako wykonane.",
                            en=f"Task #{task_id} is already marked done.",
                        )
                    )
                    return
                item["done"] = True
                self._save_state()
                await message.channel.send(
                    tr(
                        pl=f"Oznaczono jako wykonane: #{task_id} {item.get('title', '')}",
                        en=f"Marked as done: #{task_id} {item.get('title', '')}",
                    )
                )
                return

        await message.channel.send(
            tr(pl=f"Nie znaleziono zadania #{task_id}.", en=f"Task #{task_id} not found.")
        )

    async def _task_remove(self, message, raw_id: str) -> None:
        task_id = self._parse_task_id(raw_id)
        if task_id is None:
            await message.channel.send(
                tr(
                    pl="Podaj numer zadania: `!task remove <id>`.",
                    en="Provide task number: `!task remove <id>`.",
                )
            )
            return

        tasks = self._user_tasks(message)
        for idx, item in enumerate(tasks):
            if item.get("id") == task_id:
                removed = tasks.pop(idx)
                self._save_state()
                await message.channel.send(
                    tr(
                        pl=f"Usunieto zadanie #{task_id}: {removed.get('title', '')}",
                        en=f"Removed task #{task_id}: {removed.get('title', '')}",
                    )
                )
                return

        await message.channel.send(
            tr(pl=f"Nie znaleziono zadania #{task_id}.", en=f"Task #{task_id} not found.")
        )

    async def _task_stats(self, message) -> None:
        tasks = self._user_tasks(message)
        total = len(tasks)
        done = sum(1 for item in tasks if item.get("done"))
        open_count = total - done
        await message.channel.send(
            tr(
                pl=f"Statystyki zadan: otwarte={open_count}, wykonane={done}, wszystkie={total}",
                en=f"Task stats: open={open_count}, done={done}, total={total}",
            )
        )

    @staticmethod
    def _parse_task_id(raw_id: str) -> int | None:
        raw_id = raw_id.strip()
        if not raw_id or not raw_id.isdigit():
            return None
        value = int(raw_id)
        if value <= 0:
            return None
        return value

    @staticmethod
    def _task_help() -> str:
        return tr(
            pl=(
                "Komendy taskera:\n"
                "`!task add <tresc>` - dodaj zadanie\n"
                "`!task list` - lista zadan\n"
                "`!task done <id>` - oznacz jako wykonane\n"
                "`!task remove <id>` - usun zadanie\n"
                "`!task stats` - podsumowanie\n"
                "`!task help` - pomoc\n"
                "`!roll <expr>` - rzut koscmi (np. 2d6+1)"
            ),
            en=(
                "Task commands:\n"
                "`!task add <text>` - add task\n"
                "`!task list` - list tasks\n"
                "`!task done <id>` - mark as done\n"
                "`!task remove <id>` - remove task\n"
                "`!task stats` - summary\n"
                "`!task help` - help\n"
                "`!roll <expr>` - roll dice (e.g. 2d6+1)"
            ),
        )
