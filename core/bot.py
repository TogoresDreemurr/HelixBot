from __future__ import annotations

import json
import os
from pathlib import Path

import discord
from discord import app_commands


class HelixBot(discord.Client):
    def __init__(self, *, intents: discord.Intents) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    @staticmethod
    def _parse_int_env(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print(f"ENV WARN: {name} must be an integer. Using default={default}.")
            return default

    def _state_file(self) -> Path:
        root_dir = Path(__file__).resolve().parents[1]
        data_dir = root_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "bot_runtime_state.json"

    def _next_restart_count(self) -> int:
        state_file = self._state_file()
        restart_count = 0

        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            restart_count = int(payload.get("restart_count", 0))
        except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
            restart_count = 0

        restart_count += 1
        try:
            state_file.write_text(
                json.dumps({"restart_count": restart_count}, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"STATE WARN: failed to persist restart counter: {exc}")
        return restart_count

    async def _reset_guild_commands(self, guild: discord.abc.Snowflake) -> None:
        # Sync empty once to delete stale remote guild commands, then restore local ones.
        current = list(self.tree.get_commands(guild=guild))
        self.tree.clear_commands(guild=guild)
        await self.tree.sync(guild=guild)
        for cmd in current:
            self.tree.add_command(cmd, guild=guild)

    async def setup_hook(self) -> None:
        guild_id = os.environ["DISCORD_GUILD_ID"]
        guild = discord.Object(id=int(guild_id))
        reset = os.getenv("DISCORD_RESET_COMMANDS", "").strip() == "1"
        reset_global = os.getenv("DISCORD_RESET_GLOBAL", "").strip() == "1"
        routine_enabled = os.getenv("DISCORD_ROUTINE_SYNC_ENABLED", "1").strip() != "0"
        routine_every = self._parse_int_env("DISCORD_ROUTINE_SYNC_EVERY_RESTARTS", 5)
        restart_count = self._next_restart_count()

        print(f"BOT RESTART COUNT: {restart_count}")

        routine_due = False
        if not routine_enabled:
            print("ROUTINE SYNC: disabled via DISCORD_ROUTINE_SYNC_ENABLED=0 (not recommended).")
        elif routine_every <= 0:
            print("ROUTINE SYNC: disabled because DISCORD_ROUTINE_SYNC_EVERY_RESTARTS <= 0.")
        else:
            routine_due = restart_count % routine_every == 0

        if reset_global:
            # One-time purge of global commands that can linger across guilds.
            self.tree.clear_commands(guild=None)
            synced = await self.tree.sync()
            print(f"GLOBAL RESET: synced {len(synced)} global command(s) after purge")
        if reset:
            print("MANUAL RESET: DISCORD_RESET_COMMANDS=1, pruning guild commands now.")
            await self._reset_guild_commands(guild)
        elif routine_due:
            print(
                "ROUTINE SYNC: executing safety guild command reset "
                f"(every {routine_every} restarts, now at {restart_count})."
            )
            await self._reset_guild_commands(guild)

        local_commands = [cmd.name for cmd in self.tree.get_commands(guild=guild)]
        print(f"LOCAL COMMANDS (guild): {local_commands}")
        synced = await self.tree.sync(guild=guild)
        print(f"SYNC RETURN: {synced}")
        print(f"SYNC COUNT: {len(synced)}")
        print(f"SYNC DONE: synced {len(synced)} guild command(s)")


async def on_ready_handler(bot: HelixBot) -> None:
    user = bot.user
    if user is None:
        print("Bot is ready, but user is None")
        return
    print(f"Logged in as {user} (ID: {user.id})")


def build_bot() -> HelixBot:
    intents = discord.Intents.default()
    intents.message_content = True
    return HelixBot(intents=intents)


def get_token_from_env() -> str:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")
    return token
