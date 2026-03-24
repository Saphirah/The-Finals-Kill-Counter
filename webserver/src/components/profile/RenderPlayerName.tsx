import React from "react";

export function RenderPlayerName({ name, style }: { name: string; style?: React.CSSProperties }) {
  const idx = name.lastIndexOf("#");
  if (idx > 0) {
    const base = name.slice(0, idx);
    const tag = name.slice(idx);
    return (
      <span style={style}>
        <span>{base}</span>
        <span style={{ color: "var(--text-muted)", fontSize: "0.85em", marginLeft: 6 }}>{tag}</span>
      </span>
    );
  }
  return <span style={style}>{name}</span>;
}

export default RenderPlayerName;
