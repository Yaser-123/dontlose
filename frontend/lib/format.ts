import type { Severity } from "./types";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "No date";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function daysLabel(days: number): string {
  if (days < 0) return `${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} overdue`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `${days} days left`;
}

export function monthLabel(iso: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(iso);
  if (!match) return "Undated";
  const date = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function severityClass(severity: Severity): string {
  if (severity === "overdue" || severity === "critical") return "bg-clay/10 text-clay border-clay/30";
  if (severity === "high") return "bg-gold/15 text-gold border-gold/30";
  if (severity === "medium") return "bg-navy-900/5 text-navy-800 border-navy-800/15";
  return "bg-white text-mist border-line";
}

export function toLocalInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function remindBefore(due: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(due);
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 9, 0, 0, 0)
    : new Date();
  date.setDate(date.getDate() - 3);
  if (date.getTime() < Date.now()) {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);
    return toLocalInput(tomorrow);
  }
  return toLocalInput(date);
}

export function localInputToIso(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error("Choose a valid date and time.");
  }
  return date.toISOString();
}
