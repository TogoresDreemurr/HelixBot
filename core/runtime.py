from __future__ import annotations

import os
from pathlib import Path
import json
from typing import Iterable

from dotenv import load_dotenv

from discord import app_commands
import discord

from plugin_manager.manager import PluginManager
from .i18n import tr
from .bot import HelixBot, build_bot, get_token_from_env, on_ready_handler


def _parse_id_list(value: str) -> set[int]:
    result: set[int] = set()
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            result.add(int(raw))
        except ValueError:
            continue
    return result


def _get_admin_ids() -> tuple[set[int], set[int]]:
    user_ids = _parse_id_list(os.getenv("HELIX_ADMIN_USER_IDS", ""))
    role_ids = _parse_id_list(os.getenv("HELIX_ADMIN_ROLE_IDS", ""))
    return user_ids, role_ids


def _is_admin(interaction: app_commands.Interaction, user_ids: set[int], role_ids: set[int]) -> bool:
    user = interaction.user
    if user is None:
        return False

    if user.id in user_ids:
        return True

    guild = interaction.guild
    if guild is None:
        return False

    if role_ids and isinstance(user, discord.Member):
        for role in user.roles:
            if role.id in role_ids:
                return True

    if not user_ids and not role_ids:
        return guild.owner_id == user.id

    return False


def _format_list(title: str, items: Iterable[str]) -> str:
    items = list(items)
    if not items:
        return tr(pl=f"{title}: (brak)", en=f"{title}: (none)")
    return f"{title}: {', '.join(items)}"


def _persist_enabled() -> bool:
    return os.getenv("HELIX_PERSIST_PLUGINS", "1").strip() != "0"


def _state_file(data_dir: Path) -> Path:
    return data_dir / "loaded_plugins.json"


def _load_persisted_plugins(data_dir: Path) -> list[str]:
    path = _state_file(data_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("plugins", [])
        if not isinstance(raw, list):
            return []
        return [str(name) for name in raw if str(name).strip()]
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return []


def _save_persisted_plugins(data_dir: Path, plugins: Iterable[str]) -> None:
    path = _state_file(data_dir)
    payload = {"plugins": sorted(set(plugins))}
    try:
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    except OSError as exc:
        print(f"STATE WARN: failed to persist plugin list: {exc}")


def run() -> None:
    print("RUNTIME MODULE LOADED")
    # Prefer values from .env over stale exported shell variables.
    load_dotenv(override=True)
    bot = build_bot()
    guild = discord.Object(id=int(os.environ["DISCORD_GUILD_ID"]))
    root_dir = Path(__file__).resolve().parents[1]
    plugins_dir = root_dir / "plugins"
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    manager = PluginManager(plugins_dir=plugins_dir, data_dir=data_dir, bot=bot, tree=bot.tree)
    admin_user_ids, admin_role_ids = _get_admin_ids()
    persist_plugins = _persist_enabled()

    if persist_plugins:
        persisted = _load_persisted_plugins(data_dir)
        if persisted:
            print(f"PERSIST: loading plugins from state: {persisted}")
        for name in persisted:
            ok, message = manager.load(name)
            if not ok:
                print(f"PERSIST: failed to load '{name}': {message}")
        if persisted:
            _save_persisted_plugins(data_dir, manager.active.keys())
    else:
        print("PERSIST: disabled via HELIX_PERSIST_PLUGINS=0")

    @bot.tree.command(name="load", description="Load a plugin", guild=guild)
    async def load_cmd(interaction: app_commands.Interaction, plugin: str) -> None:
        if not _is_admin(interaction, admin_user_ids, admin_role_ids):
            await interaction.response.send_message(
                tr(pl="Brak uprawnien.", en="Not authorized."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = manager.load(plugin)
        if ok:
            if persist_plugins:
                _save_persisted_plugins(data_dir, manager.active.keys())
            await bot.tree.sync(guild=guild)
        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name="unload", description="Unload a plugin", guild=guild)
    async def unload_cmd(interaction: app_commands.Interaction, plugin: str) -> None:
        if not _is_admin(interaction, admin_user_ids, admin_role_ids):
            await interaction.response.send_message(
                tr(pl="Brak uprawnien.", en="Not authorized."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = manager.unload(plugin)
        if ok:
            if persist_plugins:
                _save_persisted_plugins(data_dir, manager.active.keys())
            await bot.tree.sync(guild=guild)
        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name="list", description="List loaded and available plugins", guild=guild)
    async def list_cmd(interaction: app_commands.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        loaded = sorted(manager.active.keys())
        available = manager.available_plugins()
        not_loaded = [name for name in available if name not in manager.active]
        lines = [
            _format_list(tr(pl="Zaladowane", en="Loaded"), loaded),
            _format_list(tr(pl="Niezaladowane", en="Not loaded"), not_loaded),
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @bot.tree.error
    async def on_tree_error(
        interaction: app_commands.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandNotFound):
            await bot.tree.sync(guild=guild)
            message = tr(
                pl="Rejestr komend odswiezony. Sprobuj ponownie.",
                en="Command registry refreshed. Retry the command.",
            )
        else:
            message = tr(pl=f"Komenda nieudana: {error}", en=f"Command failed: {error}")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.NotFound:
            # Interaction expired; avoid crashing the task.
            pass

    @bot.event
    async def on_ready() -> None:
        await on_ready_handler(bot)

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        await manager.dispatch_event("message", message)
        content = message.content or ""
        for trigger in list(manager.prefix_commands.keys()):
            if content == trigger or content.startswith(f"{trigger} "):
                raw_args = content[len(trigger) :].strip()
                args = raw_args.split() if raw_args else []
                manager.dispatch_prefix(trigger, message, args)

    token = get_token_from_env()
    bot.run(token)
