      1 +# HelixBot
      2 +
      3 +Modularny bot Discord w Pythonie z systemem pluginów (hot-load/unload), komendami administrac
         yjnymi slash oraz komendami tekstowymi `!`.
      4 +
      5 +## Wymagania
      6 +
      7 +- Python 3.11+ (projekt używa `venv`)
      8 +- Bot Discord z włączonym `Message Content Intent`
      9 +- Uzupełniony plik `.env`
     10 +
     11 +## Instalacja
     12 +
     13 +```bash
     14 +cd /home/ubuntu/helixbot-copy1
     15 +python3 -m venv .venv
     16 +./.venv/bin/pip install -r requirements.txt
     17 +```
     18 +
     19 +## Konfiguracja `.env`
     20 +
     21 +Minimalna konfiguracja:
     22 +
     23 +```env
     24 +DISCORD_TOKEN=...
     25 +DISCORD_GUILD_ID=...
     26 +HELIX_ADMIN_USER_IDS=123456789012345678
     27 +HELIX_ADMIN_ROLE_IDS=
     28 +BOT_LANG=pl
     29 +```
     30 +
     31 +Opcjonalne:
     32 +
     33 +```env
     34 +HELIX_PERSIST_PLUGINS=1
     35 +DISCORD_RESET_COMMANDS=0
     36 +DISCORD_RESET_GLOBAL=0
     37 +DISCORD_ROUTINE_SYNC_ENABLED=1
     38 +DISCORD_ROUTINE_SYNC_EVERY_RESTARTS=5
     39 +```
     40 +
     41 +Dla pluginu `gold_pln`:
     42 +
     43 +```env
     44 +# GoldAPI (opcjonalnie)
     45 +GOLDAPI_KEY=...
     46 +
     47 +# XTB (opcjonalnie)
     48 +XTB_USER_ID=...
     49 +XTB_PASSWORD=...
     50 +XTB_SYMBOL=GOLD
     51 +XTB_API_HOST=xapi.xtb.com
     52 +XTB_API_PORT=5124
     53 +```
     54 +
     55 +## Uruchomienie
     56 +
     57 +```bash
     58 +cd /home/ubuntu/helixbot-copy1
     59 +./.venv/bin/python main.py
     60 +```
     61 +
     62 +## Zarządzanie pluginami (slash)
     63 +
     64 +Komendy dostępne na serwerze (`DISCORD_GUILD_ID`):
     65 +
     66 +- `/load <plugin>`
     67 +- `/unload <plugin>`
     68 +- `/list`
     69 +
     70 +Uprawnienia admina:
     71 +
     72 +- użytkownik z `HELIX_ADMIN_USER_IDS`,
     73 +- lub rola z `HELIX_ADMIN_ROLE_IDS`,
     74 +- lub właściciel guildy (jeśli listy są puste).
     75 +
     76 +## Pluginy
     77 +
     78 +Aktualnie zainstalowane:
     79 +
     80 +- `smoke`
     81 +- `tasker`
     82 +- `pogoda_pl`
     83 +- `gold_pln`
     84 +
     85 +### `tasker`
     86 +
     87 +- `!task add <tresc>`
     88 +- `!task list`
     89 +- `!task done <id>`
     90 +- `!task remove <id>`
     91 +- `!task stats`
     92 +- `!task help`
     93 +- `!roll <expr>` (np. `!roll 2d6+1`)
     94 +
     95 +Stan zadań: `data/tasker/state.json`.
     96 +
     97 +### `pogoda_pl`
     98 +
     99 +- `!pogoda`
    100 +- `!pogoda <miasto>`
    101 +- `!pogoda all`
    102 +- `!pogoda help`
    103 +
    104 +Źródło: Open-Meteo (cache 5 min per miasto).
    105 +
    106 +### `gold_pln`
    107 +
    108 +- `!zloto start [interwal]` (np. `2s`, `15m`, domyślnie `30m`)
    109 +- `!zloto stop`
    110 +- `!zloto status`
    111 +- `!zloto now`
    112 +- `!zloto source`
    113 +- `!zloto source list`
    114 +- `!zloto source set <nbp|stooq|goldapi|xtb>`
    115 +- `!zloto help`
    116 +
    122 +- `xtb` (instrument z konta XTB, wymaga `XTB_USER_ID` i `XTB_PASSWORD`)
    123 +
    124 +Stan monitoringu: `data/gold_pln/state.json`.
    125 +
    126 +## Struktura projektu
    127 +
    128 +- `main.py` - entrypoint
    129 +- `core/` - runtime bota, sync komend, i18n
    130 +- `plugin_manager/` - loader, lifecycle i API pluginów
    131 +- `plugins/` - pluginy (`manifest.json` + `main.py`)
    132 +- `data/` - stan runtime i stan pluginów
    133 +- `scripts/` - testy smoke
    134 +
    135 +## Testy
    136 +
    137 +```bash
    138 +./.venv/bin/python scripts/smoke_test.py
    139 +./.venv/bin/python scripts/tasker_test.py
    140 +./.venv/bin/python scripts/pogoda_pl_test.py
    141 +```
    142 +
    143 +## Uwaga bezpieczeństwa
    144 +
    145 +- Nie commituj prawdziwego `.env` z tokenami/hasłami.
    146 +- Jeśli token bota lub hasła wyciekły, rotuj je natychmiast.
