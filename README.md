# Finals Kill Counter

Finals Kill Counter (FKC) is an automated stats tracker for the game **The Finals**. It runs a background Python monitor that detects match end-screens via OCR, extracts post-match statistics, and uploads them to a cloud database. A React web app reads from that database and displays per-player leaderboards and detailed match history in real time.

## Repository Structure

```
FinalsKillCounter/
├── logger/        Python screen monitor (data collection)
└── webserver/     React + TypeScript front-end (stats viewer)
```

## How It Works

1. The **logger** (`logger/screenshot_monitor.py`) runs in the background while you play The Finals.
   - **Phase 1**: Every second, it reads the in-game countdown timer region via OCR. A visible timer means a match is active.
   - **In-game**: Holding `Tab` triggers a side thread that reads the map name and up to 10 player names (5 friendly, 5 enemy) from the scoreboard.
   - **Phase 2**: When the timer disappears, the logger watches for the `WINNERS` or `ELIMINATED` headline. On detection, it crops the stats panel from the screen and runs OCR to extract: combat score, objective score, support score, eliminations, assists, deaths, revives, and objectives.
   - Results are saved locally as JSON files in `logger/detection_logs/` and uploaded to SpacetimeDB.

2. The **webserver** (`webserver/`) is a Vite + React SPA that subscribes to the SpacetimeDB `finalskillcounter` database and renders:
   - A players leaderboard with aggregate K/D, total games, and favorite map.
   - Per-player profile pages with K/D trend charts, score breakdown charts, map stats, match history, and most-played-with/against tables.

## Getting Started

### Logger

See [logger/README.md](logger/README.md) for full setup instructions.

**Quick start:**

```powershell
cd logger
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python screenshot_monitor.py
```

Requirements:

- Python 3.10+
- Tesseract OCR 5.x installed (Windows: `C:\Program Files\Tesseract-OCR`)
- Windows (uses `PIL.ImageGrab` for screen capture)

### Webserver

See [webserver/README.md](webserver/README.md) for full setup instructions, including how to publish the SpacetimeDB backend module.

**Quick start:**

```bash
cd webserver
npm install
npm run dev
```

Requirements:

- Node.js 18+
- A published SpacetimeDB module (database name: `finalskillcounter`)

## Components at a Glance

### Logger — `logger/`

| File                    | Role                                                |
| ----------------------- | --------------------------------------------------- |
| `screenshot_monitor.py` | Primary script: detection loop, overlay HUD, upload |
| `config_utils.py`       | Config-loading and Tesseract path resolution        |
| `image_utils.py`        | HSV color masking and OCR output sanitization       |
| `region_tester.py`      | Visual tool for adjusting screen-region coordinates |
| `color_range_tester.py` | Interactive HSV tuner for color masks               |
| `build.py`              | PyInstaller build script (produces `FKC.exe`)       |
| `config.json`           | Screen region bounds and HSV color range settings   |
| `profile.json`          | Saved player profile name (created on first run)    |
| `detection_logs/`       | Local JSON + image archives of every detected match |

### Webserver — `webserver/`

| Path                          | Role                                                 |
| ----------------------------- | ---------------------------------------------------- |
| `src/pages/PlayersPage.tsx`   | All-players leaderboard                              |
| `src/pages/PlayerProfile.tsx` | Per-player stats page                                |
| `src/components/profile/`     | Charts, tables, and atoms used by the profile page   |
| `spacetimedb/src/index.ts`    | SpacetimeDB module (schema + `submit_match` reducer) |
| `src/module_bindings/`        | Auto-generated TypeScript client bindings            |

## Configuration

The logger reads all tuneable values from `logger/config.json`. The two main sections are:

- **`regions`** — relative screen coordinates (0.0–1.0) for each OCR region. Calibrate these with `region_tester.py` if text is not being read correctly on your display.
- **`color_ranges`** — HSV masks used to isolate text before OCR. Calibrate with `color_range_tester.py`.

## Building a Standalone Logger EXE

To distribute the logger without requiring Python or Tesseract to be installed separately:

```powershell
cd logger
pip install pyinstaller
python build.py
```

The output is in `logger/dist/FKC/`. `config.json` and `profile.json` are copied automatically.

## SpacetimeDB

The project uses [SpacetimeDB](https://spacetimedb.com) (maincloud) as its real-time backend. The database is named `finalskillcounter`. The logger POSTs match data directly to the SpacetimeDB HTTP API; the webserver subscribes via WebSocket for live updates.

To publish the backend module:

```bash
cd webserver
spacetime login
spacetime publish finalskillcounter --module-path spacetimedb
```
