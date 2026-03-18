import { useMemo } from "react";
import { MatchEntry } from "../../module_bindings/types";
import { avg, kd, fmt, useSortable, isWin } from "./profileUtils";
import { Th, MapCell } from "./atoms";
import { styles } from "./profileStyles";

export function MapStatsTable({ matches }: { matches: MatchEntry[] }) {
  const sort = useSortable("avgKD");

  const mapStats = useMemo(() => {
    const groups: Record<string, MatchEntry[]> = {};
    for (const m of matches) {
      const k = m.map ?? "Unknown";
      if (!groups[k]) groups[k] = [];
      groups[k].push(m);
    }
    return Object.entries(groups)
      .map(([map, ms]) => {
        const e = avg(ms.map((m) => m.eliminations));
        const d = avg(ms.map((m) => m.deaths));
        return {
          map,
          count: ms.length,
          avgElims: e,
          avgDeaths: d,
          avgAssists: avg(ms.map((m) => m.assists)),
          avgKD: kd(e, Math.max(d, 0.01)),
          avgCombat: avg(ms.map((m) => m.combatScore)),
          avgObj: avg(ms.map((m) => m.objectiveScore)),
          avgSupport: avg(ms.map((m) => m.supportScore)),
          avgTotal: avg(ms.map((m) => (m.combatScore ?? 0) + (m.objectiveScore ?? 0) + (m.supportScore ?? 0))),
          avgRevives: avg(ms.map((m) => m.revives)),
          avgObjectives: avg(ms.map((m) => m.objectives)),
          wins: ms.filter((m) => isWin(m.win) === true).length,
          winDataCount: ms.filter((m) => isWin(m.win) !== undefined).length,
        };
      })
      .sort((a, b) => {
        const va = (a as Record<string, unknown>)[sort.key] as number;
        const vb = (b as Record<string, unknown>)[sort.key] as number;
        return sort.dir === "asc" ? va - vb : vb - va;
      });
  }, [matches, sort.key, sort.dir]);

  if (mapStats.length === 0) return null;

  return (
    <section style={styles.section}>
      <h3 style={styles.sectionTitle}>AVERAGE STATS PER MAP</h3>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr style={styles.thead}>
              <Th label="MAP" sortKey="map" sort={sort} />
              <Th label="GAMES" sortKey="count" sort={sort} />
              <Th label="AVG KD" sortKey="avgKD" sort={sort} />
              <Th label="AVG ELIMS" sortKey="avgElims" sort={sort} />
              <Th label="AVG DEATHS" sortKey="avgDeaths" sort={sort} />
              <Th label="AVG ASSISTS" sortKey="avgAssists" sort={sort} />
              <Th label="AVG COMBAT" sortKey="avgCombat" sort={sort} />
              <Th label="AVG OBJ" sortKey="avgObj" sort={sort} />
              <Th label="AVG SUPPORT" sortKey="avgSupport" sort={sort} />
              <Th label="AVG TOTAL SCORE" sortKey="avgTotal" sort={sort} />
              <Th label="AVG REVIVES" sortKey="avgRevives" sort={sort} />
              <Th label="WIN RATE" sortKey="winDataCount" sort={sort} />
            </tr>
          </thead>
          <tbody>
            {mapStats.map((row) => (
              <tr key={row.map} style={styles.trow}>
                <td style={styles.td}>
                  <MapCell map={row.map} />
                </td>
                <td style={styles.tdNum}>{row.count}</td>
                <td
                  style={{
                    ...styles.tdNum,
                    color: row.avgKD >= 1 ? "var(--green)" : "var(--red)",
                    fontWeight: 600,
                  }}
                >
                  {fmt(row.avgKD)}
                </td>
                <td style={{ ...styles.tdNum, color: "var(--green)" }}>{fmt(row.avgElims, 1)}</td>
                <td style={{ ...styles.tdNum, color: "var(--red)" }}>{fmt(row.avgDeaths, 1)}</td>
                <td style={{ ...styles.tdNum, color: "var(--blue)" }}>{fmt(row.avgAssists, 1)}</td>
                <td style={styles.tdNum}>{Math.round(row.avgCombat)}</td>
                <td style={styles.tdNum}>{Math.round(row.avgObj)}</td>
                <td style={styles.tdNum}>{Math.round(row.avgSupport)}</td>
                <td
                  style={{
                    ...styles.tdNum,
                    color: "var(--accent)",
                    fontWeight: 600,
                  }}
                >
                  {Math.round(row.avgTotal).toLocaleString()}
                </td>
                <td style={{ ...styles.tdNum, color: "var(--purple)" }}>{fmt(row.avgRevives, 1)}</td>
                <td
                  style={{
                    ...styles.tdNum,
                    fontWeight: 600,
                    color: row.winDataCount === 0 ? "var(--text-muted)" : row.wins / row.winDataCount >= 0.5 ? "var(--green)" : "var(--red)",
                  }}
                >
                  {row.winDataCount === 0 ? "—" : `${Math.round((row.wins / row.winDataCount) * 100)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
