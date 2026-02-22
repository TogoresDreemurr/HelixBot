# HelixBot

Modularny bot Discord w Pythonie z systemem pluginów (hot-load/unload), komendami administracyjnymi slash oraz komendami tekstowymi `!`.

## Wymagania

- Python 3.11+ (projekt używa `venv`)
- Bot Discord z włączonym `Message Content Intent`
- Uzupełniony plik `.env`

## Instalacja

```bash
git clone https://github.com/TogoresDreemurr/HelixBot.git
cd HelixBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
nano .env
```

## Konfiguracja `.env`

```env
DISCORD_TOKEN=Here-write-your-token
HELIX_ADMIN_USER_IDS=user_id
HELIX_ADMIN_ROLE_IDS=role_id
DISCORD_ROUTINE_SYNC_ENABLED=1
DISCORD_ROUTINE_SYNC_EVERY_RESTARTS=5
DISCORD_RESET_COMMANDS=0
BOT_LANG=en
```

## Uruchomienie

```bash
cd HelixBot
source .venv/bin/activate
docker compose up -d --build
docker compose logs -f helixbot
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
