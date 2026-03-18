# Finals Kill Counter — Logger

The logger is the data-collection component of Finals Kill Counter. The primary script is `screenshot_monitor.py`. It runs in the background while you play The Finals, automatically detecting match end-screens, extracting your post-match stats via OCR, and uploading them to SpacetimeDB.

## How It Works

The monitor uses a two-phase detection loop:

**Phase 1 — Game Detection**

Every second, it reads a small countdown-timer region in the top-center of the screen using OCR. When a `MM:SS` timer is visible, it knows a match is in progress. After 8 consecutive misses (timer gone), it transitions to Phase 2.

**Phase 2 — End-Screen Detection**

The monitor watches a dedicated region for the `WINNERS` or `ELIMINATED` headline text. When detected, it takes a full screenshot, crops the stats panel, runs OCR to extract all numeric stats, and saves the result locally and uploads it to SpacetimeDB. After a successful capture, it waits for the next game. If no end-screen appears within 2 minutes, Phase 2 times out and the loop resets.

**Tab Detection (in-game)**

While Phase 1 is running, holding the `Tab` key triggers a parallel background thread that:

- Reads the map name from the top-right corner (OCR + fuzzy match against known map names).
- Continuously captures the scoreboard region every 0.5 seconds to read player names.
- Accumulates name samples per slot (slots 0–4 = friendly team, 5–9 = enemy team) and picks the most-detected name per slot by majority vote.

Player and map data detected during the match are attached to the final stats upload.

## Prerequisites

### 1. Install Tesseract OCR (Windows)

1. Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run `tesseract-ocr-w64-setup-v5.x.x.exe` and install to the default path (`C:\Program Files\Tesseract-OCR`).
3. The script auto-detects the default installation paths. If Tesseract is installed elsewhere, update `_get_tesseract_path()` in `config_utils.py`.

Verify the installation:

```powershell
tesseract --version
```

### 2. Python Environment

```powershell
cd logger
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running the Monitor

```powershell
python screenshot_monitor.py
```

On the first run, a small setup dialog will appear asking for your player profile name. This name is attached to every uploaded match entry. It is saved in `profile.json` and reused on subsequent runs.

The monitor starts an always-on-top HUD overlay in the top-left corner of your screen showing current state. Press the `Home` key to toggle overlay visibility. The overlay can be dragged by clicking and holding anywhere on it.

Stop the monitor at any time with `Ctrl+C` or via the system tray icon.

## Overlay Information

| Field                         | Description                                           |
| ----------------------------- | ----------------------------------------------------- |
| Player                        | Your profile name                                     |
| Map                           | Last detected map name                                |
| Phase                         | 1 = watching timer, 2 = scanning end-screen           |
| Game                          | Whether the countdown timer is currently visible      |
| Last                          | Preview of the most recently extracted stats          |
| Timer / Map / Players regions | Live cropped previews of the OCR regions              |
| Friendly / Enemy              | Most-likely player names detected from Tab scoreboard |

## In-Game Workflow

1. Launch the monitor before or after starting The Finals.
2. When a match begins, Phase 1 detects the timer and starts tracking.
3. During the match, hold `Tab` to open the in-game scoreboard. The monitor will read the map name and player names automatically.
4. When the match ends:
   - The `WINNERS` or `ELIMINATED` screen triggers stat extraction automatically.
   - Stats are saved to `detection_logs/` as a JSON file.
   - Stats are uploaded to SpacetimeDB.
5. The monitor resets and waits for the next match.

## Output

### Local Detection Logs

Saved in `detection_logs/` as timestamped JSON files:

```
detection_logs/
├── detection_2026-03-18_21-00-00.json
├── detection_2026-03-18_21-00-00_original.png
├── detection_2026-03-18_21-00-00_processed.png
└── ...
```

Each JSON file contains:

```json
{
  "detection_time": "2026-03-18 21:00:00",
  "profile": "YourName",
  "similarity_score": 1.0,
  "map": "Monaco",
  "won": true,
  "stats": {
    "combat_score": 4200,
    "objective_score": 1100,
    "support_score": 800,
    "eliminations": 7,
    "assists": 3,
    "deaths": 2,
    "revives": 1,
    "objectives": 4
  },
  "players": {
    "friendly": [{"name": "Ally1"}, ...],
    "enemy": [{"name": "Opponent1"}, ...]
  }
}
```

### SpacetimeDB Upload

Every detection is also POSTed to the configured SpacetimeDB instance (`finalskillcounter` database on maincloud). The webserver reads from this database in real time.

## Configuration

All tunable values live in `config.json` next to the executable (or script).

### Screen Regions

Region bounds are stored as relative fractions of screen size (0.0–1.0), so they scale automatically to any resolution.

| Key                     | Purpose                                        |
| ----------------------- | ---------------------------------------------- |
| `countdown_region_rel`  | Where the in-game timer is read (Phase 1)      |
| `map_region_rel`        | Where the map name is read when Tab is held    |
| `players_tab_region`    | The scoreboard region scanned for player names |
| `crop_bounds_rel`       | The stats panel cropped for final OCR          |
| `eliminated_won_region` | Region checked for WINNERS/ELIMINATED text     |

Use `region_tester.py` to visually verify and adjust region coordinates for your display.

### Color Ranges

HSV color masks are used to isolate text before OCR. Each range is a `[[H_lo, S_lo, V_lo], [H_hi, S_hi, V_hi]]` pair.

| Key                        | Used for                                  |
| -------------------------- | ----------------------------------------- |
| `color_ranges_countdown`   | White countdown timer text                |
| `color_ranges_map`         | White/near-white map name text            |
| `color_ranges_endscreen`   | White and yellow stats text on end-screen |
| `color_ranges_players_tab` | White player name text on scoreboard      |

Use `color_range_tester.py` to interactively tune HSV mask parameters.

## Building a Standalone Executable

`build.py` automates a PyInstaller build that bundles Tesseract and all Python dependencies into a single `FKC.exe`:

```powershell
pip install pyinstaller
python build.py
```

The EXE is output to `dist/FKC/`. The build script also copies `config.json` (and `profile.json` if present) next to the EXE.

## Helper Scripts

| Script                  | Purpose                                             |
| ----------------------- | --------------------------------------------------- |
| `screenshot_monitor.py` | **Primary script** — run this to start logging      |
| `config_utils.py`       | Shared path and config-loading utilities            |
| `image_utils.py`        | Color masking and OCR line sanitization             |
| `region_tester.py`      | Visual tool for adjusting screen-region coordinates |
| `color_range_tester.py` | Interactive HSV color range tuner                   |
| `build.py`              | PyInstaller build script for the standalone EXE     |

## Troubleshooting

**Tesseract not found**
Run `tesseract --version`. If it is not on PATH, install it to the default location or edit `_get_tesseract_path()` in `config_utils.py`.

**Stats not detected / wrong numbers**
The stats region or color ranges may need calibration for your display. Use `region_tester.py` to verify the crop bounds and `color_range_tester.py` to tune the HSV masks, then update `config.json`.

**Map always shows "Unknown"**
Hold Tab in-game before the match ends so the monitor can read the map name. The map region must be visible and correctly configured in `config.json`.

**Player names missing or garbled**
Hold Tab for at least one second. The monitor takes multiple samples and picks the most common result per slot, so a longer hold gives better accuracy. Adjust `players_tab_region` in `config.json` if the scoreboard is not inside the configured bounds.

**Upload fails**
Check your internet connection. SpacetimeDB errors are printed to the console with the HTTP status code and response body. The local JSON log is always saved regardless of upload success.

## Known Maps

The Finals maps recognized by the fuzzy OCR matcher:

- Kyoto
- Bernal
- Las Vegas Stadium
- Monaco
- Nozomi
- Citadel
- Seoul
- Skyway Stadium
- Sys$Horizon
- Practice Range
