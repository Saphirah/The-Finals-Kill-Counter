import { useState } from "react";
import type { WinEnum } from "../../module_bindings/types";

export const avg = (vals: (number | undefined)[]) => {
  const filtered = vals.filter((v): v is number => v !== undefined && v !== null);
  return filtered.length ? filtered.reduce((a, b) => a + b, 0) / filtered.length : 0;
};

export const sum = (vals: (number | undefined)[]) => vals.reduce<number>((s, v) => s + (v ?? 0), 0);

export const kd = (e: number, d: number) => (d === 0 ? e : e / d);

export function fmt(n: number, dp = 2) {
  return n.toFixed(dp);
}

function toDate(iso: string) {
  const d = new Date(iso.replace(" ", "T"));
  return isNaN(d.getTime()) ? iso : d;
}

export function fmtDate(iso: string) {
  const d = toDate(iso);
  if (typeof d === "string") return d;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "2-digit",
  });
}

export function fmtDateTime(iso: string) {
  const d = toDate(iso);
  if (typeof d === "string") return d;
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Returns true for Win, false for Loss, undefined for Undefined/unknown
export function isWin(v: WinEnum | null | undefined): boolean | undefined {
  if (v == null) return undefined;
  if (v.tag === "Win") return true;
  if (v.tag === "Loss") return false;
  return undefined;
}

export type SortDir = "asc" | "desc";

export function useSortable(defaultKey: string, defaultDir: SortDir = "desc") {
  const [key, setKey] = useState(defaultKey);
  const [dir, setDir] = useState<SortDir>(defaultDir);
  const toggle = (k: string) => {
    if (k === key) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setKey(k);
      setDir("desc");
    }
  };
  const indicator = (k: string) => (k === key ? (dir === "asc" ? " ▲" : " ▼") : "");
  return { key, dir, toggle, indicator };
}
