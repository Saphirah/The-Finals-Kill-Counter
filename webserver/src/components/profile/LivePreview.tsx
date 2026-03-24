import { useMemo } from "react";
import { useTable } from "spacetimedb/react";
import { tables } from "../../module_bindings";
import type { MatchEntry, MatchPlayer } from "../../module_bindings/types";
import { isWin } from "./profileUtils";
import { styles } from "./profileStyles";
import RenderPlayerName from "./RenderPlayerName";
import { getMapImage } from "../../constants/mapImages";

// ── Helpers ────────────────────────────────────────────────────────────────

interface SlotPlayer {
  name: string; // "" = undetected
  isKnown: boolean;
}

function parseSlots(json: string): SlotPlayer[] {
  try {
    const arr = JSON.parse(json) as { name: string }[];
    return arr.slice(0, 5).map((p) => ({
      name: p?.name ?? "",
      isKnown: !!p?.name,
    }));
  } catch {
    return Array(5).fill({ name: "", isKnown: false });
  }
}

interface EncounterStats {
  withGames: number;
  withWins: number;
  againstGames: number;
  againstWins: number;
  mapWithGames: number;
  mapWithWins: number;
  mapAgainstGames: number;
  mapAgainstWins: number;
}

function buildEncounterStats(matches: readonly MatchEntry[], allMatchPlayers: readonly MatchPlayer[], /**myName: string,*/ mapFilter: string | null): Map<string, EncounterStats> {
  const matchById = new Map<bigint, MatchEntry>(matches.map((m) => [m.id, m]));
  //const myNameUpper = myName.toUpperCase();
  const result = new Map<string, EncounterStats>();

  const get = (name: string): EncounterStats => {
    if (!result.has(name)) {
      result.set(name, {
        withGames: 0,
        withWins: 0,
        againstGames: 0,
        againstWins: 0,
        mapWithGames: 0,
        mapWithWins: 0,
        mapAgainstGames: 0,
        mapAgainstWins: 0,
      });
    }
    return result.get(name)!;
  };

  for (const mp of allMatchPlayers) {
    const match = matchById.get(mp.matchId);
    if (!match) continue;
    if (!mp.name) continue;
    //if (mp.name.split("#")[0].toUpperCase() === myNameUpper) continue;

    const won = isWin(match.win);
    const onMap = mapFilter ? match.map === mapFilter : false;
    const s = get(mp.name);

    if (mp.friendly) {
      s.withGames++;
      if (won === true) s.withWins++;
      if (onMap) {
        s.mapWithGames++;
        if (won === true) s.mapWithWins++;
      }
    } else {
      s.againstGames++;
      if (won === true) s.againstWins++;
      if (onMap) {
        s.mapAgainstGames++;
        if (won === true) s.mapAgainstWins++;
      }
    }
  }

  return result;
}

function winRateOrNull(wins: number, games: number): number | null {
  return games > 0 ? wins / games : null;
}

function fmtPct(r: number | null): string {
  if (r === null) return "—";
  return `${Math.round(r * 100)}%`;
}

// ── W/L chips ─────────────────────────────────────────────────────────────

function WLChips({ results }: { results: boolean[] }) {
  return (
    <span style={styles.wlChipRow}>
      {results.map((w, i) => (
        <span key={i} style={styles.wlChip(w)} title={w ? "Win" : "Loss"} />
      ))}
    </span>
  );
}

// ── Player Slot Row ────────────────────────────────────────────────────────

function PlayerSlotRow({
  slot,
  friendly,
  stats,
  mapName,
  isBest,
  isDanger,
  isLast,
  isYou,
}: {
  slot: SlotPlayer;
  friendly: boolean;
  stats: EncounterStats | undefined;
  mapName: string | null;
  isBest: boolean;
  isDanger: boolean;
  isLast: boolean;
  isYou: boolean;
}) {
  const slotStyle = isLast ? styles.livePlayerSlotLast : styles.livePlayerSlot;

  if (!slot.isKnown) {
    return (
      <div style={slotStyle}>
        <span style={styles.livePlayerUnknown}>Unknown Player</span>
        <div style={styles.livePlayerStats}>
          <span>
            Assumed <span style={styles.liveStatVal}>50%</span>
          </span>
        </div>
      </div>
    );
  }

  const isNew = !stats || (friendly ? stats.withGames === 0 : stats.againstGames === 0);
  const overallRate = stats ? (friendly ? winRateOrNull(stats.withWins, stats.withGames) : winRateOrNull(stats.againstWins, stats.againstGames)) : null;
  const mapRate = stats && mapName ? (friendly ? winRateOrNull(stats.mapWithWins, stats.mapWithGames) : winRateOrNull(stats.mapAgainstWins, stats.mapAgainstGames)) : null;
  const overallGames = stats ? (friendly ? stats.withGames : stats.againstGames) : 0;

  return (
    <div style={slotStyle}>
      <div style={styles.livePlayerName}>
        {(() => {
          const nameStyle: React.CSSProperties = {
            maxWidth: 200,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: isYou ? "var(--accent)" : undefined,
          };
          return <RenderPlayerName name={slot.name} style={nameStyle} />;
        })()}
        {isNew && <span style={styles.liveBadge("new")}>NEW</span>}
        {isBest && <span style={styles.liveBadge("best")}>★ Best Ally</span>}
        {isDanger && <span style={styles.liveBadge("danger")}>⚠ Watch Out</span>}
      </div>
      <div style={styles.livePlayerStats}>
        <span>
          {friendly ? "Winrate with:" : "Winrate vs:"} <span style={styles.liveStatVal}>{fmtPct(overallRate)}</span>
          {overallGames > 0 && <span style={{ color: "var(--text-muted)", marginLeft: 3 }}>({overallGames} games)</span>}
        </span>
        {mapName && (
          <span>
            On map: <span style={styles.liveStatVal}>{fmtPct(mapRate)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

interface Props {
  playerName: string;
  allMatches: readonly MatchEntry[];
  allMatchPlayers: readonly MatchPlayer[];
}

export function LivePreview({ playerName, allMatches, allMatchPlayers }: Props) {
  const [liveRows] = useTable(tables.liveState);

  const liveState = useMemo(() => liveRows.find((r) => r.playerName === playerName) ?? null, [liveRows, playerName]);

  // Parsed player slots
  const { friendlySlots, enemySlots } = useMemo(() => {
    if (!liveState) return { friendlySlots: [], enemySlots: [] };
    return {
      friendlySlots: parseSlots(liveState.friendlyPlayers),
      enemySlots: parseSlots(liveState.enemyPlayers),
    };
  }, [liveState]);

  const mapName = liveState?.map || null;

  // Build encounter stats for all known names in this live match
  const encounterStats = useMemo(() => {
    if (!liveState) return new Map<string, EncounterStats>();
    const myMatches = allMatches.filter((m) => m.playerName === playerName);
    return buildEncounterStats(myMatches, allMatchPlayers, /**playerName,*/ mapName);
  }, [liveState, allMatches, allMatchPlayers, playerName, mapName]);

  // Map winrate + recent form (last 5 on this map)
  const { mapWinRate, mapForm } = useMemo(() => {
    if (!mapName) return { mapWinRate: null, mapForm: [] };
    const myMapMatches = allMatches.filter((m) => m.playerName === playerName && m.map === mapName).sort((a, b) => b.detectionTime.localeCompare(a.detectionTime));
    const withData = myMapMatches.filter((m) => isWin(m.win) !== undefined);
    const wins = withData.filter((m) => isWin(m.win) === true).length;
    return {
      mapWinRate: withData.length > 0 ? wins / withData.length : null,
      mapForm: withData.slice(0, 5).map((m) => isWin(m.win) === true),
    };
  }, [allMatches, playerName, mapName]);

  // Win prediction: average of (map + 5 enemy against-rates + 5 friendly with-rates)
  const winPrediction = useMemo(() => {
    const components: number[] = [mapWinRate ?? 0.5];
    for (const slot of enemySlots) {
      const s = slot.isKnown ? encounterStats.get(slot.name) : undefined;
      const rate = s ? winRateOrNull(s.againstWins, s.againstGames) : null;
      components.push(rate ?? 0.5);
    }
    for (const slot of friendlySlots) {
      const s = slot.isKnown ? encounterStats.get(slot.name) : undefined;
      const rate = s ? winRateOrNull(s.withWins, s.withGames) : null;
      components.push(rate ?? 0.5);
    }
    return components.reduce((a, b) => a + b, 0) / components.length;
  }, [friendlySlots, enemySlots, encounterStats, mapWinRate]);

  // Best teammate: highest withWinRate among detected friendlies with ≥1 game
  const bestTeammate = useMemo(() => {
    let best: string | null = null;
    let bestRate = -1;
    let bestGames = -1;
    for (const slot of friendlySlots) {
      if (!slot.isKnown) continue;
      if (slot.name.split("#")[0].toUpperCase() === playerName.toUpperCase()) continue;
      const s = encounterStats.get(slot.name);
      if (!s || s.withGames === 0) continue;
      const rate = s.withWins / s.withGames;
      if (rate > bestRate || (rate === bestRate && s.withGames > bestGames)) {
        bestRate = rate;
        best = slot.name;
        bestGames = s.withGames;
      }
    }
    return best;
  }, [friendlySlots, encounterStats, playerName]);

  // Watch out for: lowest againstWinRate among detected enemies with ≥1 game
  const watchOutFor = useMemo(() => {
    let worst: string | null = null;
    let worstRate = 2;
    for (const slot of enemySlots) {
      if (!slot.isKnown) continue;
      const s = encounterStats.get(slot.name);
      if (!s || s.againstGames === 0) continue;
      const rate = s.againstWins / s.againstGames;
      if (rate < worstRate) {
        worstRate = rate;
        worst = slot.name;
      }
    }
    return worst;
  }, [enemySlots, encounterStats]);

  // ── Idle screen ──────────────────────────────────────────────────────────
  if (!liveState) {
    return (
      <div style={styles.liveIdleWrap}>
        <div style={styles.liveIdleIcon}>📡</div>
        <div style={styles.liveIdleTitle}>No Active Match Detected</div>
        <div style={styles.liveIdleHint}>Hold Tab in-game to scan players. The live preview will populate automatically once the Python tracker sends data.</div>
      </div>
    );
  }

  const mapImg = mapName ? getMapImage(mapName) : undefined;
  const myMapMatches = allMatches.filter((m) => m.playerName === playerName && m.map === mapName);
  const mapWins = myMapMatches.filter((m) => isWin(m.win) === true).length;
  const mapTotal = myMapMatches.filter((m) => isWin(m.win) !== undefined).length;

  return (
    <div>
      {/* Map Banner */}
      <div style={styles.liveMapBanner}>
        {mapImg && <img src={mapImg} alt="" style={styles.liveMapBg} referrerPolicy="no-referrer" />}
        <div style={styles.liveMapOverlay}>
          <div>
            <div
              style={{
                fontSize: 10,
                letterSpacing: 3,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                marginBottom: 2,
              }}
            >
              Current Map
            </div>
            <div style={styles.liveMapName}>{mapName || "Unknown Map"}</div>
          </div>
          <div style={styles.liveMapStats}>
            {mapTotal > 0 && (
              <div style={styles.liveMapRecord}>
                {mapWins}W – {mapTotal - mapWins}L on this map
              </div>
            )}
            {mapForm.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    fontSize: 10,
                    letterSpacing: 2,
                    color: "var(--text-muted)",
                    textTransform: "uppercase",
                  }}
                >
                  Last {mapForm.length}
                </span>
                <WLChips results={mapForm} />
              </div>
            )}
            {mapWinRate !== null && (
              <div
                style={{
                  fontFamily: "var(--font-head)",
                  fontSize: 20,
                  fontWeight: 700,
                  color: mapWinRate >= 0.5 ? "var(--green)" : "var(--red)",
                }}
              >
                {Math.round(mapWinRate * 100)}%
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Win Prediction Banner */}
      <div style={styles.predictionBanner(winPrediction)}>
        <div style={styles.predictionPct(winPrediction)}>{Math.round(winPrediction * 100)}%</div>
        <div>
          <div style={styles.predictionLabel}>Estimated Win Probability</div>
          <div style={styles.predictionSub}>Based on your historical winrates with teammates, against enemies, and on {mapName || "this map"}. Unknown players counted as 50%.</div>
        </div>
      </div>

      {/* Player Grid */}
      <div style={styles.liveGrid}>
        {/* Friendly Team */}
        <div style={styles.liveTeamCard}>
          <div style={styles.liveTeamHeader(true)}>🟢 Your Team</div>
          {friendlySlots.map((slot, i) => (
            <PlayerSlotRow
              key={i}
              slot={slot}
              friendly={true}
              stats={slot.isKnown ? encounterStats.get(slot.name) : undefined}
              mapName={mapName}
              isBest={slot.isKnown && slot.name === bestTeammate}
              isYou={slot.isKnown && slot.name.split("#")[0].toUpperCase() === playerName.toUpperCase()}
              isDanger={false}
              isLast={i === friendlySlots.length - 1}
            />
          ))}
        </div>

        {/* Enemy Team */}
        <div style={styles.liveTeamCard}>
          <div style={styles.liveTeamHeader(false)}>🔴 Enemy Team</div>
          {enemySlots.map((slot, i) => (
            <PlayerSlotRow
              key={i}
              slot={slot}
              friendly={false}
              stats={slot.isKnown ? encounterStats.get(slot.name) : undefined}
              mapName={mapName}
              isBest={false}
              isDanger={slot.isKnown && slot.name === watchOutFor}
              isYou={slot.isKnown && slot.name.split("#")[0].toUpperCase() === playerName.toUpperCase()}
              isLast={i === enemySlots.length - 1}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
