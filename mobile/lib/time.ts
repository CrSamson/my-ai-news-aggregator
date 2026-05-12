/**
 * lib/time.ts — relative-time formatter per UI spec §9.2.
 *
 *   < 1 hour: "Just now" or "23m ago"
 *   1-24 hours: "5h ago"
 *   1-7 days: "Yesterday", "3 days ago"
 *   > 7 days: "Apr 28"
 *
 * Pure function, no React. Accepts ISO 8601 string or Date.
 */

const MS_MINUTE = 60_000;
const MS_HOUR   = 60 * MS_MINUTE;
const MS_DAY    = 24 * MS_HOUR;

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatRelativeTime(
  input: string | Date | null | undefined,
  now: Date = new Date(),
): string {
  if (!input) return "";
  const dt = typeof input === "string" ? new Date(input) : input;
  if (Number.isNaN(dt.getTime())) return "";

  const diff = now.getTime() - dt.getTime();

  if (diff < MS_MINUTE) return "Just now";

  if (diff < MS_HOUR) {
    const m = Math.floor(diff / MS_MINUTE);
    return `${m}m ago`;
  }

  if (diff < MS_DAY) {
    const h = Math.floor(diff / MS_HOUR);
    return `${h}h ago`;
  }

  if (diff < 2 * MS_DAY) return "Yesterday";

  if (diff < 7 * MS_DAY) {
    const d = Math.floor(diff / MS_DAY);
    return `${d} days ago`;
  }

  // > 7 days → "Apr 28" (no year)
  return `${MONTH_SHORT[dt.getMonth()]} ${dt.getDate()}`;
}
