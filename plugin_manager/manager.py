from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import discord
from discord import app_commands

CORE_API_VERSION = "1.0.0"

EventHandler = Callable[..., Any]
PrefixHandler = Callable[..., Any]


class PluginError(Exception):
    pass


@dataclass
class PluginHandle:
    name: str
    module_name: str
    module: ModuleType
    instance: Any
    event_handlers: list[tuple[str, EventHandler]] = field(default_factory=list)
    prefix_handlers: list[tuple[str, PrefixHandler]] = field(default_factory=list)


class PluginAPI:
    def __init__(
        self,
        manager: "PluginManager",
        plugin_name: str,
        bot: discord.Client | None,
        tree: app_commands.CommandTree | None,
    ) -> None:
        self._manager = manager
        self._plugin_name = plugin_name
        self._bot = bot
        self._tree = tree

    def register_event(self, name: str, handler: EventHandler) -> None:
        self._manager._register_event(self._plugin_name, name, handler)

    def register_prefix(self, trigger: str, handler: PrefixHandler) -> None:
        self._manager._register_prefix(self._plugin_name, trigger, handler)

    def get_data_path(self, *, create: bool = True) -> Path:
        path = self._manager.data_dir / self._plugin_name
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def bot(self) -> discord.Client | None:
        return self._bot

    @property
    def tree(self) -> app_commands.CommandTree | None:
        return self._tree

    @property
    def logger(self) -> Callable[[str], None]:
        return self._manager.logger


class PluginManager:
    def __init__(
        self,
        *,
        plugins_dir: Path,
        data_dir: Path,
        bot: discord.Client | None = None,
        tree: app_commands.CommandTree | None = None,
    ) -> None:
        self.plugins_dir = plugins_dir
        self.data_dir = data_dir
        self.active: dict[str, PluginHandle] = {}
        self.events: dict[str, list[EventHandler]] = {}
        self.prefix_commands: dict[str, list[PrefixHandler]] = {}
        self.bot = bot
        self.tree = tree

    def logger(self, message: str) -> None:
        print(f"[PluginManager] {message}")

    async def dispatch_event(self, name: str, *args: Any, **kwargs: Any) -> None:
        handlers = list(self.events.get(name, []))
        for handler in handlers:
            try:
                result = handler(*args, **kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # pragma: no cover - side effects only
                self.logger(f"Handler error for event '{name}': {exc}")

    def dispatch_prefix(self, trigger: str, *args: Any, **kwargs: Any) -> None:
        handlers = list(self.prefix_commands.get(trigger, []))
        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - side effects only
                self.logger(f"Prefix handler error for '{trigger}': {exc}")

    def available_plugins(self) -> list[str]:
        if not self.plugins_dir.is_dir():
            return []
        result: list[str] = []
        for entry in sorted(self.plugins_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest = entry / "manifest.json"
            if manifest.is_file():
                result.append(entry.name)
        return result

    def load(self, name: str) -> tuple[bool, str]:
        if name in self.active:
            return False, f"Plugin '{name}' already loaded"

        plugin_dir = self.plugins_dir / name
        if not plugin_dir.is_dir() or not (plugin_dir / "manifest.json").is_file():
            return False, f"Plugin '{name}' is not installed"

        try:
            manifest = self._load_manifest(plugin_dir)
            module_name = f"plugins.{name}"
            module = self._import_module(module_name, plugin_dir / manifest["entry"])
            instance = self._create_instance(module, manifest["class"])  # noqa: A003

            handle = PluginHandle(
                name=name,
                module_name=module_name,
                module=module,
                instance=instance,
            )
            self.active[name] = handle

            api = PluginAPI(self, name, self.bot, self.tree)
            self._safe_call(instance, "on_load", api)
            self._safe_call(instance, "on_enable")
            self.logger(f"Loaded plugin '{name}'")
            return True, f"Loaded '{name}'"
        except Exception as exc:
            self.logger(f"Failed to load plugin '{name}': {exc}")
            self._unload_partial(name)
            return False, f"Load failed: {exc}"

    def unload(self, name: str) -> tuple[bool, str]:
        handle = self.active.get(name)
        if handle is None:
            return False, f"Plugin '{name}' is not loaded"

        try:
            self._safe_call(handle.instance, "on_disable")
            self._safe_call(handle.instance, "on_unload")
        except Exception as exc:
            self.logger(f"Error during unload of '{name}': {exc}")
        finally:
            self._remove_events(name)
            self._remove_prefix(name)
            self._remove_module(handle.module_name)
            del self.active[name]

        self.logger(f"Unloaded plugin '{name}'")
        return True, f"Unloaded '{name}' (plugin data/state on disk preserved)"

    def _load_manifest(self, plugin_dir: Path) -> dict[str, Any]:
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.is_file():
            raise PluginError("manifest.json not found")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginError(f"Invalid manifest.json: {exc}") from exc

        required = {"name", "version", "api_version", "entry", "class"}
        missing = required - set(manifest.keys())
        if missing:
            raise PluginError(f"Manifest missing fields: {sorted(missing)}")

        if manifest["name"] != plugin_dir.name:
            raise PluginError("Manifest name does not match plugin directory")

        if manifest["api_version"] != CORE_API_VERSION:
            raise PluginError(
                f"API version mismatch: {manifest['api_version']} != {CORE_API_VERSION}"
            )

        entry_path = plugin_dir / manifest["entry"]
        if not entry_path.is_file():
            raise PluginError(f"Entry file not found: {entry_path}")

        return manifest

    def _import_module(self, module_name: str, entry: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_name, entry)
        if spec is None or spec.loader is None:
            raise PluginError("Failed to create import spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _create_instance(self, module: ModuleType, class_name: str) -> Any:
        if not hasattr(module, class_name):
            raise PluginError(f"Class not found in module: {class_name}")
        cls = getattr(module, class_name)
        return cls()

    def _safe_call(self, instance: Any, method: str, *args: Any) -> None:
        if not hasattr(instance, method):
            return
        func = getattr(instance, method)
        if callable(func):
            try:
                func(*args)
            except Exception as exc:
                raise PluginError(f"{method} failed: {exc}") from exc

    def _register_event(self, plugin_name: str, name: str, handler: EventHandler) -> None:
        self.events.setdefault(name, []).append(handler)
        handle = self.active.get(plugin_name)
        if handle:
            handle.event_handlers.append((name, handler))

    def _register_prefix(self, plugin_name: str, trigger: str, handler: PrefixHandler) -> None:
        self.prefix_commands.setdefault(trigger, []).append(handler)
        handle = self.active.get(plugin_name)
        if handle:
            handle.prefix_handlers.append((trigger, handler))

    def _remove_events(self, plugin_name: str) -> None:
        handle = self.active.get(plugin_name)
        if handle is None:
            return
        for name, handler in handle.event_handlers:
            handlers = self.events.get(name, [])
            self.events[name] = [h for h in handlers if h is not handler]
            if not self.events[name]:
                del self.events[name]
        handle.event_handlers.clear()

    def _remove_prefix(self, plugin_name: str) -> None:
        handle = self.active.get(plugin_name)
        if handle is None:
            return
        for trigger, handler in handle.prefix_handlers:
            handlers = self.prefix_commands.get(trigger, [])
            self.prefix_commands[trigger] = [h for h in handlers if h is not handler]
            if not self.prefix_commands[trigger]:
                del self.prefix_commands[trigger]
        handle.prefix_handlers.clear()

    def _remove_module(self, module_name: str) -> None:
        to_delete = [
            key for key in sys.modules.keys() if key == module_name or key.startswith(f"{module_name}.")
        ]
        for key in to_delete:
            del sys.modules[key]

    def _unload_partial(self, name: str) -> None:
        handle = self.active.get(name)
        if handle:
            try:
                self._safe_call(handle.instance, "on_disable")
                self._safe_call(handle.instance, "on_unload")
            except Exception:
                pass
            self._remove_events(name)
            self._remove_prefix(name)
            self._remove_module(handle.module_name)
            del self.active[name]
