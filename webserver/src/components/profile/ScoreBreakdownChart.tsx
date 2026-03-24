import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend } from "recharts";
import { MatchEntry } from "../../module_bindings/types";

export function ScoreBreakdownChart({ matches }: { matches: MatchEntry[] }) {
  const data = matches.map((m, i) => ({
    game: i + 1,
    combat: m.combatScore ?? 0,
    objective: m.objectiveScore ?? 0,
    support: m.supportScore ?? 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="game" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip
          contentStyle={{
            background: "#1a1a21",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 11,
          }}
        />
        <Bar dataKey="combat" stackId="a" fill="#fabf2b" name="Combat" />
        <Bar dataKey="objective" stackId="a" fill="rgba(255,255,255,0.55)" name="Objective" />
        <Bar dataKey="support" stackId="a" fill="#058bbe" name="Support" />
        <Legend formatter={(val) => <span style={{ color: "var(--text-sub)", fontSize: 11 }}>{val as string}</span>} />
      </BarChart>
    </ResponsiveContainer>
  );
}
