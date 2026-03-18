import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend } from "recharts";
import { KDTooltip } from "./atoms";
import { styles } from "./profileStyles";

export type KDTrendPoint = {
  game: number;
  kd: number;
  elims: number;
  deaths: number;
  label: string;
};

export function KDTrendChart({ data }: { data: KDTrendPoint[] }) {
  return (
    <div style={styles.chartCard}>
      <h3 style={styles.sectionTitle}>
        KD RATIO TREND <span style={styles.sectionHint}>(last {data.length} games)</span>
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="game" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip content={<KDTooltip />} />
          <Line type="monotone" dataKey="kd" stroke="#f5a011" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="elims" stroke="#4dde80" strokeWidth={1} dot={false} strokeDasharray="4 2" />
          <Line type="monotone" dataKey="deaths" stroke="#e84040" strokeWidth={1} dot={false} strokeDasharray="4 2" />
          <Legend formatter={(val) => <span style={{ color: "var(--text-sub)", fontSize: 11 }}>{(val as string).toUpperCase()}</span>} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
