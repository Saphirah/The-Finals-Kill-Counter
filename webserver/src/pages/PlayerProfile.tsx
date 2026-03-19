import { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTable, useSpacetimeDB } from "spacetimedb/react";
import { DbConnection, tables } from "../module_bindings";
import { sum, kd, fmt, fmtDate, isWin } from "../components/profile/profileUtils";
import { styles } from "../components/profile/profileStyles";
import { OverviewCard, SummaryBadge } from "../components/profile/atoms";
import { ScoreBreakdownChart } from "../components/profile/ScoreBreakdownChart";
import { KDTrendChart } from "../components/profile/KDTrendChart";
import { MapStatsTable } from "../components/profile/MapStatsTable";
import { MatchHistoryTable } from "../components/profile/MatchHistoryTable";
import { PlayerHeader } from "../components/profile/PlayerHeader";
import { LivePreview } from "../components/profile/LivePreview";

export default function PlayerProfile() {
  const { name } = useParams<{ name: string }>();
  const playerName = decodeURIComponent(name ?? "");
  const navigate = useNavigate();

  const [allMatches] = useTable(tables.matchEntry);
  const [allMatchPlayers] = useTable(tables.matchPlayer);
  const [tab, setTab] = useState<"alltime" | "today" | "live">("alltime");

  const matches = useMemo(() => allMatches.filter((m) => m.playerName === playerName).sort((a, b) => b.detectionTime.localeCompare(a.detectionTime)), [allMatches, playerName]);

  const todayPrefix = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, []);

  const activeMatches = useMemo(() => (tab === "today" ? matches.filter((m) => m.detectionTime.startsWith(todayPrefix)) : matches), [tab, matches, todayPrefix]);

  // Most played with / against — counts, wins, and winDataCount across ALL matches (not just today filter)
  // Each entry is [name, count, wins, winDataCount]
  const { playedWith, playedAgainst } = useMemo(() => {
    const matchIds = new Set<bigint>(matches.map((m) => m.id));
    const matchesById = new Map<bigint, (typeof matches)[0]>();
    for (const m of matches) matchesById.set(m.id, m);

    const withCounts: Record<string, number> = {};
    const withWins: Record<string, number> = {};
    const withWinData: Record<string, number> = {};
    const againstCounts: Record<string, number> = {};
    const againstWins: Record<string, number> = {};
    const againstWinData: Record<string, number> = {};
    const playerNameUpper = playerName.toUpperCase();

    const mainWinForMatch = (matchId: bigint): boolean | undefined => {
      const me = matchesById.get(matchId);
      return me ? isWin(me.win) : undefined;
    };

    for (const mp of allMatchPlayers) {
      if (!matchIds.has(mp.matchId)) continue;
      if (!mp.name) continue; // skip empty
      const baseName = mp.name.split("#")[0].toUpperCase();
      if (baseName === playerNameUpper) continue; // skip self

      const result = mainWinForMatch(mp.matchId);
      if (mp.friendly) {
        withCounts[mp.name] = (withCounts[mp.name] ?? 0) + 1;
        if (result === true) withWins[mp.name] = (withWins[mp.name] ?? 0) + 1;
        if (result !== undefined) withWinData[mp.name] = (withWinData[mp.name] ?? 0) + 1;
      } else {
        againstCounts[mp.name] = (againstCounts[mp.name] ?? 0) + 1;
        if (result === true) againstWins[mp.name] = (againstWins[mp.name] ?? 0) + 1;
        if (result !== undefined) againstWinData[mp.name] = (againstWinData[mp.name] ?? 0) + 1;
      }
    }

    const toSorted = (counts: Record<string, number>, wins: Record<string, number>, winData: Record<string, number>) =>
      Object.entries(counts)
        .map(([name, count]) => [name, count, wins[name] ?? 0, winData[name] ?? 0] as [string, number, number, number])
        .sort((a, b) => b[1] - a[1]);

    return {
      playedWith: toSorted(withCounts, withWins, withWinData),
      playedAgainst: toSorted(againstCounts, againstWins, againstWinData),
    };
  }, [matches, allMatchPlayers, playerName]);

  const overview = useMemo(() => {
    const totalElims = sum(activeMatches.map((m) => m.eliminations));
    const totalDeaths = sum(matches.map((m) => m.deaths));
    const totalAssists = sum(matches.map((m) => m.assists));
    const totalRevives = sum(matches.map((m) => m.revives));
    const totalObjectives = sum(matches.map((m) => m.objectives));
    const totalCombat = sum(matches.map((m) => m.combatScore));
    const totalObj = sum(matches.map((m) => m.objectiveScore));
    const totalSupport = sum(matches.map((m) => m.supportScore));
    const totalScore = totalCombat + totalObj + totalSupport;

    const n = activeMatches.length;
    const avgElims = n ? totalElims / n : 0;
    const avgDeaths = n ? totalDeaths / n : 0;
    const avgAssists = n ? totalAssists / n : 0;
    const avgKD = kd(totalElims, totalDeaths);
    const avgScore = n ? totalScore / n : 0;

    const mapGroups: Record<string, typeof activeMatches> = {};
    for (const m of activeMatches) {
      const k = m.map ?? "Unknown";
      if (!mapGroups[k]) mapGroups[k] = [];
      mapGroups[k].push(m);
    }
    const mapKDs = Object.entries(mapGroups).map(([map, ms]) => ({
      map,
      kd: kd(sum(ms.map((m) => m.eliminations)), Math.max(sum(ms.map((m) => m.deaths)), 1)),
      count: ms.length,
    }));
    const bestMap = [...mapKDs].sort((a, b) => b.kd - a.kd)[0];
    const favMap = [...mapKDs].sort((a, b) => b.count - a.count)[0];

    const bestGameElims = Math.max(...activeMatches.map((m) => m.eliminations ?? 0), 0);
    const bestGameKD = Math.max(...activeMatches.map((m) => kd(m.eliminations ?? 0, Math.max(m.deaths ?? 0, 1))), 0);
    const bestGameDeaths = Math.max(...activeMatches.map((m) => m.deaths ?? 0), 0);
    const bestGameAssists = Math.max(...activeMatches.map((m) => m.assists ?? 0), 0);
    const bestGameRevives = Math.max(...activeMatches.map((m) => m.revives ?? 0), 0);
    const bestGameObjectives = Math.max(...activeMatches.map((m) => m.objectives ?? 0), 0);
    const bestGameCombat = Math.max(...activeMatches.map((m) => m.combatScore ?? 0), 0);
    const bestGameObjScore = Math.max(...activeMatches.map((m) => m.objectiveScore ?? 0), 0);
    const bestGameSupport = Math.max(...activeMatches.map((m) => m.supportScore ?? 0), 0);
    const bestGameTotal = Math.max(...activeMatches.map((m) => (m.combatScore ?? 0) + (m.objectiveScore ?? 0) + (m.supportScore ?? 0)), 0);

    return {
      games: n,
      totalElims,
      totalDeaths,
      totalAssists,
      totalRevives,
      totalObjectives,
      avgElims,
      avgDeaths,
      avgAssists,
      avgKD,
      avgScore,
      bestMap,
      favMap,
      bestGameElims,
      bestGameKD,
      bestGameDeaths,
      bestGameAssists,
      bestGameRevives,
      bestGameObjectives,
      bestGameCombat,
      bestGameObjScore,
      bestGameSupport,
      bestGameTotal,
    };
  }, [activeMatches]);

  const kdTrend = useMemo(() => {
    return [...activeMatches]
      .reverse()
      .slice(-20)
      .map((m, i) => ({
        game: i + 1,
        kd: parseFloat(kd(m.eliminations ?? 0, Math.max(m.deaths ?? 0, 1)).toFixed(2)),
        elims: m.eliminations ?? 0,
        deaths: m.deaths ?? 0,
        label: fmtDate(m.detectionTime),
      }));
  }, [activeMatches]);

  if (matches.length === 0 && allMatches.length > 0) {
    return (
      <div
        style={{
          ...styles.page,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <p style={{ color: "var(--text-sub)" }}>
          No matches found for <strong>{playerName}</strong>.
        </p>
        <button style={styles.backBtn} onClick={() => navigate("/")}>
          ← Back
        </button>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <PlayerHeader playerName={playerName} gameCount={overview.games} onBack={() => navigate("/")} />

      <div style={styles.content}>
        {/* Tab bar */}
        <div style={tabBar}>
          <button style={tab === "alltime" ? activeTab : inactiveTab} onClick={() => setTab("alltime")}>
            ALL TIME
          </button>
          <button style={tab === "today" ? activeTab : inactiveTab} onClick={() => setTab("today")}>
            TODAY
            {tab === "today" && activeMatches.length === 0 ? "" : tab === "today" ? ` (${activeMatches.length})` : ""}
          </button>
          <button style={tab === "live" ? liveActiveTab : liveInactiveTab} onClick={() => setTab("live")}>
            <span style={liveDot} />
            LIVE
          </button>
        </div>

        {/* LIVE tab */}
        {tab === "live" && <LivePreview playerName={playerName} allMatches={allMatches} allMatchPlayers={allMatchPlayers} />}

        {tab !== "live" && (
          <>
            {/* overview averages */}
            <section style={styles.section}>
              <h3 style={styles.sectionTitle}>GLOBAL TOTALS</h3>
              <div style={styles.cardGrid}>
                <SummaryBadge label="Games Played" value={overview.games} color="var(--green)" />
                <SummaryBadge label="Total Elims" value={overview.totalElims} color="var(--green)" />
                <SummaryBadge label="Total Deaths" value={overview.totalDeaths} color="var(--red)" />
                <SummaryBadge label="Total Assists" value={overview.totalAssists} color="var(--blue)" />
                <SummaryBadge label="Total Revives" value={overview.totalRevives} color="var(--purple)" />
                <SummaryBadge label="Total Objectives" value={overview.totalObjectives} color="var(--accent)" />
              </div>
            </section>

            <section style={styles.section}>
              <h3 style={styles.sectionTitle}>GLOBAL AVERAGES</h3>
              <div style={styles.cardGrid}>
                <OverviewCard label="OVERALL KD" value={fmt(overview.avgKD)} icon="⚔️" color={overview.avgKD >= 1 ? "var(--green)" : "var(--red)"} />
                <OverviewCard label="AVG ELIMS" value={fmt(overview.avgElims, 1)} icon="💀" color="var(--green)" />
                <OverviewCard label="AVG DEATHS" value={fmt(overview.avgDeaths, 1)} icon="☠️" color="var(--red)" />
                <OverviewCard label="AVG ASSISTS" value={fmt(overview.avgAssists, 1)} icon="🤝" color="var(--blue)" />
                <OverviewCard label="AVG SCORE" value={Math.round(overview.avgScore).toLocaleString()} icon="🏆" color="var(--accent)" />
              </div>
            </section>

            {/* career highs */}
            <section style={styles.section}>
              <h3 style={styles.sectionTitle}>
                SINGLE GAME RECORDS <span style={styles.sectionHint}>(career highs)</span>
              </h3>
              <div style={styles.cardGrid}>
                <OverviewCard label="MOST ELIMS" value={overview.bestGameElims} icon="🏆" color="var(--green)" />
                <OverviewCard label="BEST KD" value={`${fmt(overview.bestGameKD)}`} icon="⚔️" color="var(--accent)" />
                <OverviewCard label="MOST DEATHS" value={overview.bestGameDeaths} icon="☠️" color="var(--red)" />
                <OverviewCard label="MOST ASSISTS" value={overview.bestGameAssists} icon="🤝" color="var(--blue)" />
                <OverviewCard label="MOST REVIVES" value={overview.bestGameRevives} icon="💉" color="var(--purple)" />
                <OverviewCard label="MOST OBJECTIVES" value={overview.bestGameObjectives} icon="🎯" color="var(--accent)" />
                <OverviewCard label="BEST COMBAT" value={overview.bestGameCombat.toLocaleString()} icon="⚡" color="var(--green)" />
                <OverviewCard label="BEST OBJ SCORE" value={overview.bestGameObjScore.toLocaleString()} icon="📦" color="var(--blue)" />
                <OverviewCard label="BEST SUPPORT" value={overview.bestGameSupport.toLocaleString()} icon="🛡️" color="var(--purple)" />
                <OverviewCard label="BEST TOTAL SCORE" value={overview.bestGameTotal.toLocaleString()} icon="🏅" color="var(--accent)" />
              </div>
            </section>

            {/* charts */}
            {kdTrend.length >= 2 && (
              <section style={styles.section}>
                <div style={styles.chartsRow}>
                  <KDTrendChart data={kdTrend} />
                  <div style={styles.chartCard}>
                    <h3 style={styles.sectionTitle}>
                      SCORE BREAKDOWN <span style={styles.sectionHint}>(last {Math.min(kdTrend.length, 10)} games)</span>
                    </h3>
                    <ScoreBreakdownChart matches={[...matches].reverse().slice(-10)} />
                  </div>
                </div>
              </section>
            )}

            {tab === "today" && activeMatches.length === 0 && (
              <section style={styles.section}>
                <p
                  style={{
                    color: "var(--text-sub)",
                    fontSize: 14,
                    textAlign: "center",
                    padding: "32px 0",
                  }}
                >
                  No matches recorded today yet.
                </p>
              </section>
            )}
            <MapStatsTable matches={activeMatches} />
            {(playedWith.length > 0 || playedAgainst.length > 0) && <PlayerEncountersTable playedWith={playedWith} playedAgainst={playedAgainst} />}

            <MatchHistoryTable matches={activeMatches} />
            <MatchImporter playerName={playerName} />
          </>
        )}
      </div>
    </div>
  );
}

// ── Player Encounters Table ─────────────────────────────────────────────────

const ENC_PAGE_SIZE = 10;

function EncounterSubTable({ title, data, color }: { title: string; data: [string, number, number, number][]; color: string }) {
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(data.length / ENC_PAGE_SIZE));
  const slice = data.slice(page * ENC_PAGE_SIZE, (page + 1) * ENC_PAGE_SIZE);

  return (
    <div style={encTableWrap}>
      <div
        style={{
          padding: "12px 16px 0",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span style={{ ...encSubTitle, color }}>{title}</span>
      </div>
      <table style={encTable}>
        <thead>
          <tr>
            <th style={encTh}>#</th>
            <th style={encTh}>PLAYER</th>
            <th style={{ ...encTh, textAlign: "right" }}>MATCHES</th>
            <th style={{ ...encTh, textAlign: "right" }}>WIN RATE</th>
          </tr>
        </thead>
        <tbody>
          {slice.length === 0 ? (
            <tr>
              <td
                colSpan={4}
                style={{
                  ...encTd,
                  color: "var(--text-muted)",
                  textAlign: "center",
                  padding: "20px 0",
                }}
              >
                Coming Soon
              </td>
            </tr>
          ) : (
            slice.map(([name, count, wins, winDataCount], i) => (
              <tr key={name} style={encRow} onClick={() => navigate(`/player/${encodeURIComponent(name)}`)}>
                <td style={{ ...encTd, color: "var(--text-muted)", width: 32 }}>{page * ENC_PAGE_SIZE + i + 1}</td>
                <td
                  style={{
                    ...encTd,
                    color: "var(--accent)",
                    cursor: "pointer",
                  }}
                >
                  {name}
                </td>
                <td
                  style={{
                    ...encTd,
                    textAlign: "right",
                    fontWeight: 600,
                    color: "var(--green)",
                  }}
                >
                  {count}
                </td>
                <td
                  style={{
                    ...encTd,
                    textAlign: "right",
                    color: "var(--text-muted)",
                  }}
                >
                  {winDataCount > 0 ? `${Math.round((wins / winDataCount) * 100)}%` : "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div style={encPagination}>
          <button style={{ ...encPageBtn, opacity: page === 0 ? 0.35 : 1 }} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            ← PREV
          </button>
          <span
            style={{
              color: "var(--text-muted)",
              fontSize: 11,
              letterSpacing: 1,
            }}
          >
            {page + 1} / {totalPages}
          </span>
          <button
            style={{
              ...encPageBtn,
              opacity: page === totalPages - 1 ? 0.35 : 1,
            }}
            disabled={page === totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            NEXT →
          </button>
        </div>
      )}
    </div>
  );
}

function PlayerEncountersTable({ playedWith, playedAgainst }: { playedWith: [string, number, number, number][]; playedAgainst: [string, number, number, number][] }) {
  return (
    <section style={styles.section}>
      <h3 style={styles.sectionTitle}>PLAYER ENCOUNTERS</h3>
      <div style={encGrid}>
        <EncounterSubTable title="FRIENDLY TEAM" data={playedWith} color="var(--green)" />
        <EncounterSubTable title="ENEMY TEAM" data={playedAgainst} color="var(--red)" />
      </div>
    </section>
  );
}

const encGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 20,
};

const encTableWrap: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  overflow: "hidden",
};

const encSubTitle: React.CSSProperties = {
  fontFamily: "var(--font-head)",
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: 3,
  textTransform: "uppercase" as const,
  display: "block",
  paddingBottom: 10,
};

const encTable: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
};

const encTh: React.CSSProperties = {
  fontFamily: "var(--font-head)",
  fontSize: 10,
  letterSpacing: 2,
  color: "var(--text-muted)",
  padding: "8px 16px",
  textAlign: "left" as const,
  background: "var(--bg-card)",
  borderBottom: "1px solid var(--border)",
};

const encRow: React.CSSProperties = {
  cursor: "pointer",
};

const encTd: React.CSSProperties = {
  fontSize: 13,
  color: "var(--text)",
  padding: "8px 16px",
  borderBottom: "1px solid rgba(255,255,255,0.04)",
};

const encPagination: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "10px 16px",
  borderTop: "1px solid var(--border)",
};

const encPageBtn: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--border)",
  color: "var(--text-sub)",
  padding: "4px 12px",
  borderRadius: 4,
  fontFamily: "var(--font-head)",
  fontSize: 10,
  letterSpacing: 1,
  cursor: "pointer",
};

// Removed old Most Played With / Against section — consolidated into PLAYER ENCOUNTERS

// ── Tab styles ──────────────────────────────────────────────────────────────

const tabBar: React.CSSProperties = {
  display: "flex",
  gap: 4,
  marginBottom: 28,
  borderBottom: "1px solid var(--border)",
  paddingBottom: 0,
};

const baseTab: React.CSSProperties = {
  background: "transparent",
  border: "none",
  borderBottom: "2px solid transparent",
  color: "var(--text-sub)",
  padding: "8px 20px",
  fontFamily: "var(--font-head)",
  fontSize: 13,
  letterSpacing: 2,
  cursor: "pointer",
  marginBottom: -1,
  transition: "color 0.15s, border-color 0.15s",
};

const activeTab: React.CSSProperties = {
  ...baseTab,
  color: "var(--accent)",
  borderBottomColor: "var(--accent)",
  fontWeight: 700,
};

const inactiveTab: React.CSSProperties = {
  ...baseTab,
};

const liveActiveTab: React.CSSProperties = {
  ...baseTab,
  color: "var(--green)",
  borderBottomColor: "var(--green)",
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
  gap: 6,
};

const liveInactiveTab: React.CSSProperties = {
  ...baseTab,
  display: "flex",
  alignItems: "center",
  gap: 6,
};

const liveDot: React.CSSProperties = {
  width: 7,
  height: 7,
  borderRadius: "50%",
  background: "var(--green)",
  flexShrink: 0,
  boxShadow: "0 0 6px var(--green)",
};

// ── JSON Match Importer ─────────────────────────────────────────────────────

// Camelcase flat format (manual / exported)
type RawMatchCamel = {
  detectionTime?: string;
  map?: string;
  similarityScore?: number;
  combatScore?: number;
  objectiveScore?: number;
  supportScore?: number;
  eliminations?: number;
  assists?: number;
  deaths?: number;
  revives?: number;
  objectives?: number;
  playerName?: string;
  win?: boolean;
};

// Snake_case format from the logger
type RawMatchLogger = {
  detection_time?: string;
  profile?: string;
  similarity_score?: number;
  map?: string;
  stats?: {
    combat_score?: number;
    objective_score?: number;
    support_score?: number;
    eliminations?: number;
    assists?: number;
    deaths?: number;
    revives?: number;
    objectives?: number;
  };
};

type RawMatch = RawMatchCamel | RawMatchLogger;

// Normalise any supported format to a flat camelCase object ready for submitMatch
function normaliseMatch(raw: RawMatch): RawMatchCamel | null {
  // Logger format: has detection_time or profile
  if ("detection_time" in raw || "profile" in raw) {
    const r = raw as RawMatchLogger;
    if (!r.detection_time) return null;
    return {
      detectionTime: r.detection_time,
      playerName: r.profile,
      map: r.map,
      similarityScore: r.similarity_score,
      combatScore: r.stats?.combat_score,
      objectiveScore: r.stats?.objective_score,
      supportScore: r.stats?.support_score,
      eliminations: r.stats?.eliminations,
      assists: r.stats?.assists,
      deaths: r.stats?.deaths,
      revives: r.stats?.revives,
      objectives: r.stats?.objectives,
    };
  }
  // Camelcase flat format
  const r = raw as RawMatchCamel;
  if (!r.detectionTime) return null;
  return r;
}

function MatchImporter({ playerName }: { playerName: string }) {
  const connState = useSpacetimeDB();
  const conn = connState.getConnection() as DbConnection | null;
  const fileRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  // Try to extract a RawMatch array from any reasonable JSON shape
  const extractMatches = (parsed: unknown): RawMatch[] | null => {
    if (Array.isArray(parsed)) return parsed as RawMatch[];
    if (parsed && typeof parsed === "object") {
      const obj = parsed as Record<string, unknown>;
      // Single match object — logger or camel format
      if ("detection_time" in obj || "detectionTime" in obj) return [obj as RawMatch];
      // Wrapper object: { matches: [...] } or { data: [...] } etc.
      for (const key of ["matches", "data", "entries", "results"]) {
        const val = obj[key];
        if (Array.isArray(val)) return val as RawMatch[];
      }
    }
    return null;
  };

  const readFileAsText = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (ev) => resolve(ev.target?.result as string);
      reader.onerror = reject;
      reader.readAsText(file);
    });

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setStatus(null);
    setImporting(true);

    let totalCount = 0;
    const errors: string[] = [];

    for (const file of files) {
      try {
        const text = await readFileAsText(file);
        const parsed = JSON.parse(text);
        const matches = extractMatches(parsed);
        if (!matches) {
          errors.push(`${file.name}: unrecognised JSON structure`);
          continue;
        }
        for (const raw of matches) {
          const m = normaliseMatch(raw);
          if (!m) continue;
          conn?.reducers.submitMatch({
            playerName: m.playerName ?? playerName,
            detectionTime: m.detectionTime!,
            map: m.map ?? "",
            win: m.win ?? true,
            similarityScore: m.similarityScore ?? 1,
            combatScore: m.combatScore ?? -1,
            objectiveScore: m.objectiveScore ?? -1,
            supportScore: m.supportScore ?? -1,
            eliminations: m.eliminations ?? -1,
            assists: m.assists ?? -1,
            deaths: m.deaths ?? -1,
            revives: m.revives ?? -1,
            objectives: m.objectives ?? -1,
            friendlyPlayers: "[]",
            enemyPlayers: "[]",
          });
          totalCount++;
        }
      } catch {
        errors.push(`${file.name}: failed to parse`);
      }
    }

    setImporting(false);
    if (fileRef.current) fileRef.current.value = "";

    if (errors.length > 0 && totalCount === 0) {
      setStatus(`❌ ${errors.join("; ")}`);
    } else if (errors.length > 0) {
      setStatus(`⚠️ Submitted ${totalCount} match${totalCount !== 1 ? "es" : ""}. Errors: ${errors.join("; ")}`);
    } else {
      setStatus(`✅ Submitted ${totalCount} match${totalCount !== 1 ? "es" : ""} from ${files.length} file${files.length !== 1 ? "s" : ""}.`);
    }
  };

  return (
    <section style={{ marginBottom: 40 }}>
      <h3
        style={{
          fontFamily: "var(--font-head)",
          fontSize: 16,
          fontWeight: 600,
          letterSpacing: 3,
          color: "var(--text-sub)",
          marginBottom: 16,
          textTransform: "uppercase" as const,
        }}
      >
        IMPORT MATCHES
      </h3>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          padding: "20px 24px",
          display: "flex",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap" as const,
        }}
      >
        <input ref={fileRef} type="file" accept=".json,application/json" multiple onChange={handleFile} disabled={importing} style={{ display: "none" }} id="match-import-input" />
        <label
          htmlFor="match-import-input"
          style={{
            background: "var(--accent)",
            border: "none",
            color: "#000",
            padding: "9px 20px",
            borderRadius: 6,
            fontFamily: "var(--font-head)",
            fontSize: 12,
            letterSpacing: 2,
            fontWeight: 700,
            cursor: importing ? "not-allowed" : "pointer",
            opacity: importing ? 0.6 : 1,
            userSelect: "none" as const,
          }}
        >
          {importing ? "IMPORTING…" : "📂 UPLOAD JSON"}
        </label>
        <span
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            flex: 1,
            minWidth: 200,
          }}
        >
          Upload one or more JSON files. Each match needs a unique <code style={{ color: "var(--accent)" }}>detectionTime</code> field.
        </span>
        {status && (
          <span
            style={{
              fontSize: 13,
              color: status.startsWith("✅") ? "var(--green)" : "var(--red)",
              fontFamily: "var(--font-head)",
              letterSpacing: 1,
            }}
          >
            {status}
          </span>
        )}
      </div>
    </section>
  );
}
