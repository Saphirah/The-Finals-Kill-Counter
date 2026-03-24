import { useMemo, useState, useRef, useEffect } from "react";
import { useTable, useSpacetimeDB } from "spacetimedb/react";
import { DbConnection, tables } from "../../module_bindings";
import { MatchEntry, MatchPlayer } from "../../module_bindings/types";
import { kd, fmt, fmtDateTime, useSortable, isWin } from "./profileUtils";
import { Th, MapCell } from "./atoms";
import RenderPlayerName from "./RenderPlayerName";
import { styles } from "./profileStyles";

const PAGE_SIZE = 15;

// ── Edit Modal ──────────────────────────────────────────────────────────────

type EditForm = {
  map: string;
  eliminations: string;
  deaths: string;
  assists: string;
  revives: string;
  objectives: string;
  combatScore: string;
  objectiveScore: string;
  supportScore: string;
  win: string;
};

function EditModal({ match, onClose }: { match: MatchEntry; onClose: () => void }) {
  const connState = useSpacetimeDB();
  const conn = connState.getConnection() as DbConnection | null;
  const [form, setForm] = useState<EditForm>({
    map: match.map ?? "",
    eliminations: String(match.eliminations ?? -1),
    deaths: String(match.deaths ?? -1),
    assists: String(match.assists ?? -1),
    revives: String(match.revives ?? -1),
    objectives: String(match.objectives ?? -1),
    combatScore: String(match.combatScore ?? -1),
    objectiveScore: String(match.objectiveScore ?? -1),
    supportScore: String(match.supportScore ?? -1),
    win: String((isWin(match.win) ?? true) ? "win" : "loss"),
  });

  const set = (key: keyof EditForm, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const save = () => {
    const n = (v: string) => {
      const parsed = parseInt(v, 10);
      return isNaN(parsed) ? -1 : parsed;
    };
    conn?.reducers.updateMatch({
      id: match.id,
      map: form.map,
      eliminations: n(form.eliminations),
      deaths: n(form.deaths),
      assists: n(form.assists),
      revives: n(form.revives),
      objectives: n(form.objectives),
      combatScore: n(form.combatScore),
      objectiveScore: n(form.objectiveScore),
      supportScore: n(form.supportScore),
      win: form.win === "win",
    });
    onClose();
  };

  return (
    <div style={modalOverlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={modalBox}>
        <div style={modalHeader}>
          <span style={modalTitle}>EDIT MATCH</span>
          <span style={modalDate}>{fmtDateTime(match.detectionTime)}</span>
        </div>
        <div style={modalGrid}>
          <ModalField label="Map" value={form.map} onChange={(v) => set("map", v)} isText />
          <ModalField label="Eliminations" value={form.eliminations} onChange={(v) => set("eliminations", v)} />
          <ModalField label="Deaths" value={form.deaths} onChange={(v) => set("deaths", v)} />
          <ModalField label="Assists" value={form.assists} onChange={(v) => set("assists", v)} />
          <ModalField label="Revives" value={form.revives} onChange={(v) => set("revives", v)} />
          <ModalField label="Objectives" value={form.objectives} onChange={(v) => set("objectives", v)} />
          <ModalField label="Combat Score" value={form.combatScore} onChange={(v) => set("combatScore", v)} />
          <ModalField label="Objective Score" value={form.objectiveScore} onChange={(v) => set("objectiveScore", v)} />
          <div>
            <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Win</label>
            <select value={form.win} onChange={(e) => set("win", e.target.value)} style={{ ...fieldInput, width: "100%", padding: "8px" }}>
              <option value="win">Win</option>
              <option value="loss">Loss</option>
              <option value="undefined">Unknown</option>
            </select>
          </div>
          <ModalField label="Support Score" value={form.supportScore} onChange={(v) => set("supportScore", v)} />
        </div>
        <p style={modalHint}>Use -1 for stats that were not captured.</p>
        <div style={modalActions}>
          <button style={cancelBtn} onClick={onClose}>
            Cancel
          </button>
          <button style={saveBtn} onClick={save}>
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalField({ label, value, onChange, isText }: { label: string; value: string; onChange: (v: string) => void; isText?: boolean }) {
  return (
    <div style={fieldWrap}>
      <label style={fieldLabel}>{label}</label>
      <input style={fieldInput} type={isText ? "text" : "number"} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
// ── Detail Modal ───────────────────────────────────────────────────────────────

function StatCell({ label, value, color }: { label: string; value: string | number | null | undefined; color?: string }) {
  return (
    <div style={statCellWrap}>
      <span style={{ ...statCellVal, color: color ?? "var(--text)" }}>{value === null || value === undefined ? "—" : value}</span>
      <span style={statCellLabel}>{label}</span>
    </div>
  );
}

function TeamList({ label, players, color }: { label: string; players: MatchPlayer[]; color: string }) {
  return (
    <div style={teamListWrap}>
      <div style={{ ...teamListHeader, color }}>{label}</div>
      {players.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: 12, padding: "8px 0" }}>No data</div>
      ) : (
        players.map((p, i) => (
          <div key={p.id.toString()} style={teamPlayerRow}>
            <span style={teamPlayerIndex}>{i + 1}</span>
            <span style={{ display: "inline-block", maxWidth: 220 }}>
              <RenderPlayerName name={p.name || "—"} style={teamPlayerName} />
            </span>
          </div>
        ))
      )}
    </div>
  );
}

function DetailModal({ match, allMatchPlayers, onClose }: { match: MatchEntry; allMatchPlayers: readonly MatchPlayer[]; onClose: () => void }) {
  const players = allMatchPlayers.filter((p) => p.matchId === match.id);
  const friendly = players.filter((p) => p.friendly);
  const enemy = players.filter((p) => !p.friendly);
  const total = (match.combatScore ?? 0) + (match.objectiveScore ?? 0) + (match.supportScore ?? 0);
  const matchKD = kd(match.eliminations ?? 0, Math.max(match.deaths ?? 0, 1));

  return (
    <div style={modalOverlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={detailBox}>
        <div style={detailHeader}>
          <div>
            <div style={modalTitle}>MATCH DETAILS</div>
            <div style={modalDate}>
              {fmtDateTime(match.detectionTime)}
              {match.map ? ` · ${match.map}` : ""}
            </div>
          </div>
          <button style={closeBtn} onClick={onClose}>
            ✕
          </button>
        </div>

        {isWin(match.win) !== undefined && (
          <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                fontFamily: "var(--font-head)",
                fontSize: 13,
                fontWeight: 700,
                letterSpacing: 3,
                padding: "4px 14px",
                borderRadius: 6,
                background: isWin(match.win) === true ? "rgba(5,139,190,0.15)" : "rgba(201,37,65,0.15)",
                color: isWin(match.win) === true ? "var(--green)" : "var(--red)",
                border: `1px solid ${isWin(match.win) === true ? "var(--green)" : "var(--red)"}`,
              }}
            >
              {isWin(match.win) === true ? "🏆 WIN" : "💀 LOSS"}
            </span>
          </div>
        )}
        <div style={detailStatsGrid}>
          <StatCell label="ELIMS" value={match.eliminations} color="var(--green)" />
          <StatCell label="DEATHS" value={match.deaths} color="var(--red)" />
          <StatCell label="KD" value={fmt(matchKD)} color="var(--accent)" />
          <StatCell label="ASSISTS" value={match.assists} color="var(--blue)" />
          <StatCell label="REVIVES" value={match.revives} color="var(--green)" />
          <StatCell label="OBJECTIVES" value={match.objectives} color="var(--accent)" />
          <StatCell label="COMBAT" value={match.combatScore?.toLocaleString()} />
          <StatCell label="OBJ SCORE" value={match.objectiveScore?.toLocaleString()} />
          <StatCell label="SUPPORT" value={match.supportScore?.toLocaleString()} />
          <StatCell label="TOTAL SCORE" value={total > 0 ? total.toLocaleString() : null} color="var(--accent)" />
        </div>

        <div style={detailTeamsRow}>
          <TeamList label="FRIENDLY TEAM" players={friendly} color="var(--green)" />
          <TeamList label="ENEMY TEAM" players={enemy} color="var(--red)" />
        </div>
      </div>
    </div>
  );
}
// ── Row Actions Menu ────────────────────────────────────────────────────────

function RowMenu({ match, onClose, onEdit }: { match: MatchEntry; onClose: () => void; onEdit: () => void }) {
  const connState = useSpacetimeDB();
  const conn = connState.getConnection() as DbConnection | null;
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  const handleDelete = () => {
    onClose();
    if (window.confirm(`Delete match from ${fmtDateTime(match.detectionTime)}? This cannot be undone.`)) {
      conn?.reducers.deleteMatch({ id: match.id });
    }
  };

  return (
    <div ref={ref} style={menuBox}>
      <button
        style={menuItem}
        onMouseEnter={(e) => ((e.target as HTMLElement).style.background = "var(--bg-surface)")}
        onMouseLeave={(e) => ((e.target as HTMLElement).style.background = "transparent")}
        onClick={() => {
          onClose();
          onEdit();
        }}
      >
        ✏️ Edit Stats
      </button>
      <button
        style={{ ...menuItem, color: "var(--red)" }}
        onMouseEnter={(e) => ((e.target as HTMLElement).style.background = "var(--bg-surface)")}
        onMouseLeave={(e) => ((e.target as HTMLElement).style.background = "transparent")}
        onClick={handleDelete}
      >
        🗑️ Delete Match
      </button>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

export function MatchHistoryTable({ matches }: { matches: MatchEntry[] }) {
  const sort = useSortable("detectionTime");
  const [page, setPage] = useState(0);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [editingMatch, setEditingMatch] = useState<MatchEntry | null>(null);
  const [detailMatch, setDetailMatch] = useState<MatchEntry | null>(null);
  const [allMatchPlayers] = useTable(tables.matchPlayer);

  const sortedMatches = useMemo(() => {
    return [...matches].sort((a, b) => {
      const va = (a as Record<string, unknown>)[sort.key] ?? 0;
      const vb = (b as Record<string, unknown>)[sort.key] ?? 0;
      if (typeof va === "string") return sort.dir === "asc" ? va.localeCompare(vb as string) : (vb as string).localeCompare(va);
      return sort.dir === "asc" ? (va as number) - (vb as number) : (vb as number) - (va as number);
    });
  }, [matches, sort.key, sort.dir]);

  const pagedMatches = sortedMatches.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pageCount = Math.ceil(sortedMatches.length / PAGE_SIZE);

  if (matches.length === 0) return null;

  return (
    <section style={styles.section}>
      <h3 style={styles.sectionTitle}>
        MATCH HISTORY <span style={styles.sectionHint}>({matches.length} games)</span>
      </h3>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr style={styles.thead}>
              <Th label="DATE" sortKey="detectionTime" sort={sort} />
              <Th label="MAP" sortKey="map" sort={sort} />
              <Th label="ELIMS" sortKey="eliminations" sort={sort} />
              <Th label="DEATHS" sortKey="deaths" sort={sort} />
              <Th label="KD" sortKey="eliminations" sort={sort} noSort />
              <Th label="ASSISTS" sortKey="assists" sort={sort} />
              <Th label="REVIVES" sortKey="revives" sort={sort} />
              <Th label="OBJECTIVES" sortKey="objectives" sort={sort} />
              <Th label="COMBAT" sortKey="combatScore" sort={sort} />
              <Th label="OBJ SCORE" sortKey="objectiveScore" sort={sort} />
              <Th label="SUPPORT" sortKey="supportScore" sort={sort} />
              <Th label="TOTAL SCORE" sortKey="combatScore" sort={sort} noSort />
              <Th label="WIN" sortKey="" sort={sort} noSort />
              <th style={styles.th} />
            </tr>
          </thead>
          <tbody>
            {pagedMatches.map((m) => {
              const matchKD = kd(m.eliminations ?? 0, Math.max(m.deaths ?? 0, 1));
              const total = (m.combatScore ?? 0) + (m.objectiveScore ?? 0) + (m.supportScore ?? 0);
              const rowKey = m.id.toString();
              return (
                <tr key={rowKey} style={{ ...styles.trow, cursor: "pointer" }} onClick={() => setDetailMatch(m)}>
                  <td style={styles.td}>{fmtDateTime(m.detectionTime)}</td>
                  <td style={styles.td}>
                    <MapCell map={m.map} />
                  </td>
                  <td
                    style={{
                      ...styles.tdNum,
                      color: "var(--green)",
                      fontWeight: 600,
                    }}
                  >
                    {m.eliminations ?? "—"}
                  </td>
                  <td style={{ ...styles.tdNum, color: "var(--red)" }}>{m.deaths ?? "—"}</td>
                  <td
                    style={{
                      ...styles.tdNum,
                      color: "var(--accent)",
                      fontWeight: 600,
                    }}
                  >
                    {fmt(matchKD)}
                  </td>
                  <td style={{ ...styles.tdNum, color: "var(--blue)" }}>{m.assists ?? "—"}</td>
                  <td style={{ ...styles.tdNum, color: "var(--green)" }}>{m.revives ?? "—"}</td>
                  <td style={{ ...styles.tdNum, color: "var(--accent)" }}>{m.objectives ?? "—"}</td>
                  <td style={styles.tdNum}>{m.combatScore?.toLocaleString() ?? "—"}</td>
                  <td style={styles.tdNum}>{m.objectiveScore?.toLocaleString() ?? "—"}</td>
                  <td style={styles.tdNum}>{m.supportScore?.toLocaleString() ?? "—"}</td>
                  <td
                    style={{
                      ...styles.tdNum,
                      color: "var(--accent)",
                      fontWeight: 600,
                    }}
                  >
                    {total > 0 ? total.toLocaleString() : "—"}
                  </td>
                  <td style={{ ...styles.tdNum, width: 64, textAlign: "center", paddingRight: 8 }}>
                    {isWin(m.win) === true ? (
                      <span style={{ color: "var(--green)", fontWeight: 700 }}>W</span>
                    ) : isWin(m.win) === false ? (
                      <span style={{ color: "var(--red)", fontWeight: 700 }}>L</span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td
                    style={{
                      ...styles.td,
                      position: "relative",
                      width: 40,
                      padding: "4px 8px",
                    }}
                  >
                    <button
                      style={dotsBtn}
                      title="Actions"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId((prev) => (prev === rowKey ? null : rowKey));
                      }}
                    >
                      ⋯
                    </button>
                    {openMenuId === rowKey && <RowMenu match={m} onClose={() => setOpenMenuId(null)} onEdit={() => setEditingMatch(m)} />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <div style={styles.pagination}>
          <button style={styles.pageBtn} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            ← PREV
          </button>
          <span style={{ color: "var(--text-sub)", fontSize: 12 }}>
            Page {page + 1} / {pageCount}
          </span>
          <button style={styles.pageBtn} disabled={page >= pageCount - 1} onClick={() => setPage((p) => p + 1)}>
            NEXT →
          </button>
        </div>
      )}

      {detailMatch && <DetailModal match={detailMatch} allMatchPlayers={allMatchPlayers} onClose={() => setDetailMatch(null)} />}
      {editingMatch && <EditModal match={editingMatch} onClose={() => setEditingMatch(null)} />}
    </section>
  );
}

// ── Inline styles ───────────────────────────────────────────────────────────

const detailBox: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  padding: "28px 32px",
  width: "100%",
  maxWidth: 640,
  boxShadow: "0 16px 48px rgba(0,0,0,0.6)",
  maxHeight: "90vh",
  overflowY: "auto",
};

const detailHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  marginBottom: 20,
};

const detailStatsGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(5, 1fr)",
  gap: "12px 8px",
  marginBottom: 24,
  background: "var(--bg-surface)",
  borderRadius: 8,
  padding: "16px 12px",
};

const detailTeamsRow: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 16,
};

const teamListWrap: React.CSSProperties = {
  background: "var(--bg-surface)",
  borderRadius: 8,
  padding: "12px 14px",
};

const teamListHeader: React.CSSProperties = {
  fontFamily: "var(--font-head)",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 3,
  marginBottom: 10,
  textTransform: "uppercase" as const,
};

const teamPlayerRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "4px 0",
  borderBottom: "1px solid var(--border)",
};

const teamPlayerIndex: React.CSSProperties = {
  color: "var(--text-muted)",
  fontSize: 11,
  width: 16,
  flexShrink: 0,
};

const teamPlayerName: React.CSSProperties = {
  fontSize: 13,
  color: "var(--text)",
};

const statCellWrap: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 2,
};

const statCellVal: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 700,
  fontFamily: "var(--font-head)",
};

const statCellLabel: React.CSSProperties = {
  fontSize: 9,
  letterSpacing: 2,
  color: "var(--text-muted)",
  textTransform: "uppercase" as const,
};

const closeBtn: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--text-muted)",
  fontSize: 18,
  cursor: "pointer",
  padding: "0 4px",
  lineHeight: 1,
};

const dotsBtn: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--text-sub)",
  fontSize: 18,
  lineHeight: 1,
  cursor: "pointer",
  padding: "2px 6px",
  borderRadius: 4,
  letterSpacing: 1,
};

const menuBox: React.CSSProperties = {
  position: "absolute",
  right: 0,
  top: "100%",
  zIndex: 100,
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  minWidth: 160,
  boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
  overflow: "hidden",
};

const menuItem: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  background: "transparent",
  border: "none",
  color: "var(--text)",
  padding: "10px 16px",
  fontSize: 13,
  cursor: "pointer",
  fontFamily: "inherit",
  transition: "background 0.1s",
};

const modalOverlay: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.7)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalBox: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  padding: "28px 32px",
  width: "100%",
  maxWidth: 520,
  boxShadow: "0 16px 48px rgba(0,0,0,0.6)",
};

const modalHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  marginBottom: 20,
};

const modalTitle: React.CSSProperties = {
  fontFamily: "var(--font-head)",
  fontSize: 16,
  fontWeight: 700,
  letterSpacing: 3,
  color: "var(--accent)",
};

const modalDate: React.CSSProperties = {
  fontSize: 12,
  color: "var(--text-sub)",
};

const modalGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: "12px 20px",
};

const fieldWrap: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const fieldLabel: React.CSSProperties = {
  fontSize: 10,
  letterSpacing: 2,
  color: "var(--text-muted)",
  textTransform: "uppercase",
};

const fieldInput: React.CSSProperties = {
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  color: "var(--text)",
  padding: "6px 10px",
  fontSize: 14,
  fontFamily: "inherit",
  outline: "none",
};

const modalHint: React.CSSProperties = {
  marginTop: 14,
  fontSize: 11,
  color: "var(--text-muted)",
  letterSpacing: 0.5,
};

const modalActions: React.CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: 10,
  marginTop: 20,
};

const cancelBtn: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--border)",
  color: "var(--text-sub)",
  padding: "8px 18px",
  borderRadius: 6,
  fontFamily: "var(--font-head)",
  fontSize: 12,
  letterSpacing: 2,
  cursor: "pointer",
};

const saveBtn: React.CSSProperties = {
  background: "var(--accent)",
  border: "none",
  color: "#000",
  padding: "8px 20px",
  borderRadius: 6,
  fontFamily: "var(--font-head)",
  fontSize: 12,
  letterSpacing: 2,
  fontWeight: 700,
  cursor: "pointer",
};
