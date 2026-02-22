# HelixBot

Modularny bot Discord w Pythonie z systemem pluginów (hot-load/unload), komendami administracyjnymi slash oraz komendami tekstowymi `!`.

## Wymagania

- Python 3.11+ (projekt używa `venv`)
- Bot Discord z włączonym `Message Content Intent`
- Uzupełniony plik `.env`

## Instalacja

```bash
cd /home/ubuntu/helixbot-copy1
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Konfiguracja `.env`

Minimalna konfiguracja:

```env
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...
HELIX_ADMIN_USER_IDS=123456789012345678
HELIX_ADMIN_ROLE_IDS=
BOT_LANG=pl
```

Opcjonalne:

```env
HELIX_PERSIST_PLUGINS=1
DISCORD_RESET_COMMANDS=0
DISCORD_RESET_GLOBAL=0
DISCORD_ROUTINE_SYNC_ENABLED=1
DISCORD_ROUTINE_SYNC_EVERY_RESTARTS=5
```

Dla pluginu `gold_pln`:

```env
# GoldAPI (opcjonalnie)
GOLDAPI_KEY=...

# XTB (opcjonalnie)
XTB_USER_ID=...
XTB_PASSWORD=...
XTB_SYMBOL=GOLD
XTB_API_HOST=xapi.xtb.com
XTB_API_PORT=5124
```

## Uruchomienie

```bash
cd /home/ubuntu/helixbot-copy1
./.venv/bin/python main.py
```

## Zarządzanie pluginami (slash)

Komendy dostępne na serwerze (`DISCORD_GUILD_ID`):

- `/load <plugin>`
- `/unload <plugin>`
- `/list`

Uprawnienia admina:

- użytkownik z `HELIX_ADMIN_USER_IDS`,
- lub rola z `HELIX_ADMIN_ROLE_IDS`,
- lub właściciel guildy (jeśli listy są puste).

## Pluginy

Aktualnie zainstalowane:

- `smoke`
- `tasker`
- `pogoda_pl`
- `gold_pln`

### `tasker`

- `!task add <tresc>`
- `!task list`
- `!task done <id>`
- `!task remove <id>`
- `!task stats`
- `!task help`
- `!roll <expr>` (np. `!roll 2d6+1`)

Stan zadań: `data/tasker/state.json`.

### `pogoda_pl`

- `!pogoda`
- `!pogoda <miasto>`
- `!pogoda all`
- `!pogoda help`

Źródło: Open-Meteo (cache 5 min per miasto).

### `gold_pln`

- `!zloto start [interwal]` (np. `2s`, `15m`, domyślnie `30m`)
- `!zloto stop`
- `!zloto status`
- `!zloto now`
- `!zloto source`
- `!zloto source list`
- `!zloto source set <nbp|stooq|goldapi|xtb>`
- `!zloto help`

Obsługiwane źródła:

- `nbp` (PLN/g, referencyjne)
- `stooq` (XAUUSD, USD/oz)
- `goldapi` (XAU/USD, USD/oz, wymaga `GOLDAPI_KEY`)
- `xtb` (instrument z konta XTB, wymaga `XTB_USER_ID` i `XTB_PASSWORD`)

Stan monitoringu: `data/gold_pln/state.json`.

## Struktura projektu

- `main.py` - entrypoint
- `core/` - runtime bota, sync komend, i18n
- `plugin_manager/` - loader, lifecycle i API pluginów
- `plugins/` - pluginy (`manifest.json` + `main.py`)
- `data/` - stan runtime i stan pluginów
- `scripts/` - testy smoke

## Testy

```bash
./.venv/bin/python scripts/smoke_test.py
./.venv/bin/python scripts/tasker_test.py
./.venv/bin/python scripts/pogoda_pl_test.py
```

## Uwaga bezpieczeństwa

- Nie commituj prawdziwego `.env` z tokenami/hasłami.
- Jeśli token bota lub hasła wyciekły, rotuj je natychmiast.
