import { getMapImage } from "../../constants/mapImages";
import { useSortable } from "./profileUtils";
import { styles } from "./profileStyles";

export function OverviewCard({ label, value, icon, color }: { label: string; value: string | number; icon: string; color?: string }) {
  return (
    <div style={styles.overviewCard}>
      <div style={styles.overviewIcon}>{icon}</div>
      <div style={{ ...styles.overviewValue, color: color ?? "var(--text)" }}>{value}</div>
      <div style={styles.overviewLabel}>{label}</div>
    </div>
  );
}

export function SummaryBadge({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div style={styles.summaryBadge}>
      <span style={{ ...styles.summaryVal, color }}>{value}</span>
      <span style={styles.summaryLbl}>{label}</span>
    </div>
  );
}

export function Th({ label, sortKey, sort, noSort }: { label: string; sortKey: string; sort: ReturnType<typeof useSortable>; noSort?: boolean }) {
  return (
    <th style={{ ...styles.th, cursor: noSort ? "default" : "pointer" }} onClick={() => !noSort && sort.toggle(sortKey)}>
      {label}
      {noSort ? "" : sort.indicator(sortKey)}
    </th>
  );
}

export function KDTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string; stroke: string }[]; label?: string | number }) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: "#1a1a21",
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 12,
      }}
    >
      <p style={{ color: "var(--text-sub)", marginBottom: 4 }}>Game {label}</p>
      {payload.map((e) => (
        <p key={e.name} style={{ color: e.stroke }}>
          {e.name.toUpperCase()}: <strong>{e.value}</strong>
        </p>
      ))}
    </div>
  );
}

export function MapCell({ map }: { map: string | undefined }) {
  const img = getMapImage(map);
  return (
    <div style={styles.mapCell}>
      {img && <img src={img} alt="" style={styles.mapThumb} referrerPolicy="no-referrer" />}
      <span>{map ?? "—"}</span>
    </div>
  );
}
