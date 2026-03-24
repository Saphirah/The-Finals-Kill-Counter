import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTable } from "spacetimedb/react";
import { tables } from "../module_bindings";
import { useSpacetimeDB } from "spacetimedb/react";
import { getMapImage } from "../constants/mapImages";
import RenderPlayerName from "../components/profile/RenderPlayerName";

// ── helpers ────────────────────────────────────────────────────────────────
function kd(elims: number, deaths: number) {
  return deaths === 0 ? elims : elims / deaths;
}

function toTime(iso: string) {
  const d = new Date(iso.replace(" ", "T"));
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

const FINALS_LOGO = (
  <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
    <rect width="56" height="56" rx="8" fill="#1a1a21" />
    <polygon points="28,10 46,42 10,42" fill="#f5a011" opacity="0.85" />
    <polygon points="28,18 40,38 16,38" fill="#0c0c0f" />
  </svg>
);

// ── component ──────────────────────────────────────────────────────────────
export default function PlayersPage() {
  const navigate = useNavigate();
  const conn = useSpacetimeDB();
  const connected = conn.isActive;

  const [players, playersLoading] = useTable(tables.player);
  const [allMatches] = useTable(tables.matchEntry);

  const playerStats = useMemo(() => {
    return [...players]
      .map((p) => {
        const matches = allMatches.filter((m) => m.playerName === p.name);
        const elims = matches.reduce((s, m) => s + (m.eliminations ?? 0), 0);
        const deaths = matches.reduce((s, m) => s + (m.deaths ?? 0), 0);
        const assists = matches.reduce((s, m) => s + (m.assists ?? 0), 0);
        const totalScore = matches.reduce((s, m) => s + (m.combatScore ?? 0) + (m.objectiveScore ?? 0) + (m.supportScore ?? 0), 0);

        // Favorite map
        const mapCount: Record<string, number> = {};
        for (const m of matches) {
          const map = m.map ?? "Unknown";
          mapCount[map] = (mapCount[map] ?? 0) + 1;
        }
        const favoriteMap = Object.entries(mapCount).sort((a, b) => b[1] - a[1])[0]?.[0];

        // First/last match date
        const sorted = [...matches].sort((a, b) => a.detectionTime.localeCompare(b.detectionTime));
        const firstMatch = sorted[0]?.detectionTime;
        const lastMatch = sorted[sorted.length - 1]?.detectionTime;

        return {
          name: p.name,
          games: matches.length,
          elims,
          deaths,
          assists,
          kd: kd(elims, deaths),
          avgScore: matches.length ? totalScore / matches.length : 0,
          favoriteMap,
          firstMatch,
          lastMatch,
        };
      })
      .sort((a, b) => b.games - a.games);
  }, [players, allMatches]);

  return (
    <div style={styles.page}>
      {/* ── header ───────────────────────────────────────────────────── */}
      <header style={styles.header}>
        <div style={styles.headerInner}>
          <div style={styles.logoRow}>
            {FINALS_LOGO}
            <div>
              <h1 style={styles.title}>THE FINALS</h1>
              <p style={styles.subtitle}>KILL COUNTER &nbsp;/&nbsp; STATS TRACKER</p>
            </div>
          </div>
          <div
            style={{
              ...styles.badge,
              background: connected ? "rgba(5,139,190,0.15)" : "rgba(201,37,65,0.15)",
              color: connected ? "var(--green)" : "var(--red)",
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "currentColor",
                display: "inline-block",
                marginRight: 6,
              }}
            />
            {connected ? "LIVE" : "OFFLINE"}
          </div>
        </div>
      </header>

      {/* ── body ─────────────────────────────────────────────────────── */}
      <main style={styles.main}>
        {(!connected || playersLoading) && players.length === 0 ? (
          <div style={styles.empty}>
            <div style={styles.spinner} />
            <p style={{ color: "var(--text-sub)", marginTop: 16 }}>{connected ? "Loading players…" : "Connecting to SpacetimeDB…"}</p>
          </div>
        ) : playerStats.length === 0 ? (
          <div style={styles.empty}>
            <p style={{ color: "var(--text-sub)", fontSize: 18 }}>No players yet.</p>
            <p style={{ color: "var(--text-muted)", marginTop: 8 }}>Start the Python logger to record your first match.</p>
          </div>
        ) : (
          <div style={styles.grid}>
            {playerStats.map((p) => (
              <PlayerCard key={p.name} p={p} onClick={() => navigate(`/player/${encodeURIComponent(p.name)}`)} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

// ── PlayerCard ─────────────────────────────────────────────────────────────
type PlayerStat = {
  name: string;
  games: number;
  elims: number;
  deaths: number;
  assists: number;
  kd: number;
  avgScore: number;
  favoriteMap: string | undefined;
  firstMatch: string | undefined;
  lastMatch: string | undefined;
};

function PlayerCard({ p, onClick }: { p: PlayerStat; onClick: () => void }) {
  const mapImg = getMapImage(p.favoriteMap);
  return (
    <div
      style={styles.card}
      onClick={onClick}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)";
        (e.currentTarget as HTMLElement).style.background = "var(--bg-card-hover)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLElement).style.background = "var(--bg-card)";
      }}
    >
      {/* map thumbnail strip */}
      {mapImg && (
        <div style={styles.cardBanner}>
          <img src={mapImg} alt={p.favoriteMap} style={styles.cardBannerImg} referrerPolicy="no-referrer" />
          <div style={styles.cardBannerOverlay} />
        </div>
      )}
      <div style={styles.cardBody}>
        {/* initials avatar */}
        <div style={styles.avatar}>{p.name.slice(0, 2).toUpperCase()}</div>
        <h2 style={styles.playerName}>
          <RenderPlayerName name={p.name} />
        </h2>

        {p.lastMatch && <p style={styles.lastSeen}>Last match: {toTime(p.lastMatch)}</p>}

        <div style={styles.statsRow}>
          <StatChip label="GAMES" value={p.games} />
          <StatChip label="KD" value={p.kd.toFixed(2)} color={p.kd >= 1 ? "var(--green)" : "var(--red)"} />
          <StatChip label="ELIMS" value={p.elims} />
        </div>

        {p.favoriteMap && <div style={styles.mapBadge}>🗺 {p.favoriteMap}</div>}

        <button style={styles.viewBtn}>VIEW STATS →</button>
      </div>
    </div>
  );
}

function StatChip({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={styles.chip}>
      <span style={{ ...styles.chipVal, color: color ?? "var(--text)" }}>{value}</span>
      <span style={styles.chipLabel}>{label}</span>
    </div>
  );
}

// ── styles ─────────────────────────────────────────────────────────────────
const styles = {
  page: {
    minHeight: "100vh",
    background: "var(--bg-page)",
    display: "flex",
    flexDirection: "column" as const,
  },
  header: {
    borderBottom: "1px solid var(--border)",
    background: "linear-gradient(180deg, #14141c 0%, #0c0c0f 100%)",
  },
  headerInner: {
    maxWidth: 1600,
    margin: "0 auto",
    padding: "20px 24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  logoRow: {
    display: "flex",
    alignItems: "center",
    gap: 16,
  },
  title: {
    fontFamily: "var(--font-head)",
    fontSize: 32,
    fontWeight: 700,
    letterSpacing: 3,
    color: "var(--accent)",
    lineHeight: 1,
  },
  subtitle: {
    fontFamily: "var(--font-head)",
    fontSize: 13,
    letterSpacing: 4,
    color: "var(--text-sub)",
    marginTop: 2,
  },
  badge: {
    padding: "5px 14px",
    borderRadius: 20,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 2,
    display: "flex",
    alignItems: "center",
  },
  main: {
    maxWidth: 1600,
    margin: "0 auto",
    padding: "40px 24px",
    width: "100%",
    flex: 1,
  },
  empty: {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 300,
  },
  spinner: {
    width: 36,
    height: 36,
    border: "3px solid var(--border)",
    borderTop: "3px solid var(--accent)",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
    gap: 20,
  },
  card: {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-lg)",
    overflow: "hidden",
    cursor: "pointer",
    transition: "border-color 0.15s, background 0.15s",
  },
  cardBanner: {
    height: 90,
    position: "relative" as const,
    overflow: "hidden",
  },
  cardBannerImg: {
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
  },
  cardBannerOverlay: {
    position: "absolute" as const,
    inset: 0,
    background: "linear-gradient(to bottom, transparent 30%, #1a1a21 100%)",
  },
  cardBody: {
    padding: "16px 20px 20px",
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: "50%",
    background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dim) 100%)",
    color: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-head)",
    fontWeight: 700,
    fontSize: 15,
    letterSpacing: 1,
    marginBottom: 10,
  },
  playerName: {
    fontFamily: "var(--font-head)",
    fontSize: 24,
    fontWeight: 700,
    letterSpacing: 1,
    marginBottom: 2,
  },
  lastSeen: {
    color: "var(--text-muted)",
    fontSize: 11,
    marginBottom: 14,
  },
  statsRow: {
    display: "flex",
    gap: 12,
    marginBottom: 12,
  },
  chip: {
    flex: 1,
    background: "var(--bg-surface)",
    borderRadius: 6,
    padding: "8px 4px",
    textAlign: "center" as const,
  },
  chipVal: {
    display: "block",
    fontFamily: "var(--font-head)",
    fontSize: 20,
    fontWeight: 700,
    lineHeight: 1,
  },
  chipLabel: {
    display: "block",
    fontSize: 9,
    letterSpacing: 2,
    color: "var(--text-muted)",
    marginTop: 3,
  },
  mapBadge: {
    fontSize: 11,
    color: "var(--text-sub)",
    marginBottom: 14,
  },
  viewBtn: {
    width: "100%",
    padding: "10px",
    background: "transparent",
    border: "1px solid var(--accent)",
    borderRadius: 6,
    color: "var(--accent)",
    fontFamily: "var(--font-head)",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: 2,
    transition: "background 0.15s",
  },
} as const;
