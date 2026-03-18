# Finals Kill Counter — Webserver

The webserver is the front-end component of Finals Kill Counter. It is a React + TypeScript SPA that connects to a SpacetimeDB database and displays match statistics for all tracked players in real time.

## Pages

**Players Page (`/`)**

A leaderboard showing every player whose matches have been uploaded. Each row shows:

- Total games played
- Total eliminations, deaths, assists
- K/D ratio
- Average score per match
- Favorite map
- First and last match dates

Clicking a player navigates to their profile page.

**Player Profile (`/player/:name`)**

A detailed per-player statistics view, including:

- Overview cards: total eliminations, deaths, assists, revives, objectives, K/D, average score
- All-time / Today filter toggle
- Score Breakdown chart (combat, objective, support breakdown across matches)
- K/D Trend chart over time
- Map Stats table (wins, losses, K/D, average score per map)
- Match History table (one row per match)
- Most Played With and Most Played Against tables (win rate per teammate / opponent)

## Stack

| Layer              | Technology                   |
| ------------------ | ---------------------------- |
| Frontend framework | React 18 with TypeScript     |
| Router             | React Router v7              |
| Charts             | Recharts                     |
| Build tool         | Vite 7                       |
| Database / backend | SpacetimeDB (maincloud)      |
| Client SDK         | `spacetimedb` npm package v2 |

## Prerequisites

- Node.js 18 or later
- A published SpacetimeDB module (see [SpacetimeDB Module](#spacetimedb-module) below)

## Setup

### 1. Install dependencies

```bash
cd webserver
npm install
```

### 2. Configure the SpacetimeDB connection

The database name and host are set in [src/main.tsx](src/main.tsx). The defaults point to:

```
Host:     wss://maincloud.spacetimedb.com
Database: finalskillcounter
```

If you are running a local SpacetimeDB instance, update those values to match your setup.

### 3. Start the development server

```bash
npm run dev
```

The app will be available at `http://localhost:5173` by default.

## Available Scripts

| Command                      | Description                                                        |
| ---------------------------- | ------------------------------------------------------------------ |
| `npm run dev`                | Start the Vite dev server with hot reload                          |
| `npm run build`              | Type-check and produce a production build in `dist/`               |
| `npm run preview`            | Serve the production build locally                                 |
| `npm run spacetime:generate` | Re-generate TypeScript client bindings from the SpacetimeDB module |

## SpacetimeDB Module

The backend module lives in the `spacetimedb/` sub-directory. It is written in TypeScript and compiled by the SpacetimeDB toolchain.

### Module setup

```bash
cd webserver/spacetimedb
npm install
```

### Publish to maincloud

Ensure you are logged in:

```bash
spacetime login
```

Publish the module:

```bash
spacetime publish finalskillcounter --module-path spacetimedb
```

To clear the database and republish from scratch:

```bash
spacetime publish finalskillcounter --clear-database -y --module-path spacetimedb
```

### Regenerate client bindings

After changing the module schema, regenerate the TypeScript bindings used by the frontend:

```bash
npm run spacetime:generate
```

This writes updated files to `src/module_bindings/`.

### Database schema

| Table          | Description                                                                      |
| -------------- | -------------------------------------------------------------------------------- |
| `player`       | One row per unique player name (primary key: `name`)                             |
| `match_entry`  | One row per detected match; contains all OCR-extracted stats and win/loss        |
| `match_player` | One row per player seen on the scoreboard during a match (friendly / enemy flag) |

The module exposes a single reducer, `submit_match`, which the logger calls after each detected match. Duplicate submissions (same player + detection time) are silently ignored.

## Deployment

### Static hosting

Production builds (`npm run build`) output a fully static site to `dist/`. This can be served from any static host (Nginx, Caddy, GitHub Pages, Cloudflare Pages, etc.).

### Allowed hosts (Vite dev proxy)

The `vite.config.ts` restricts the dev-server host. If you are hosting the dev server on a custom domain, add it to the `allowedHosts` list:

```ts
server: {
  allowedHosts: ["your-domain.example"],
},
```

## Troubleshooting

**Connection badge shows "Disconnected"**
The frontend failed to connect to SpacetimeDB. Verify the database name and host in `src/main.tsx` and confirm the module is published.

**No players appear on the leaderboard**
Either no matches have been uploaded yet, or the client is not subscribed to the correct tables. Check the browser console for SpacetimeDB subscription errors.

**Bindings are out of date after a schema change**
Run `npm run spacetime:generate` and rebuild.
