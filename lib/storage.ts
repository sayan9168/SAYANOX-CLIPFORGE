import { VALID_ID } from "./validation";
import { DEFAULT_RENDER, type EditorState, type RenderSettings } from "./types";

export const HISTORY_KEY = "clipforge-history-v1";
export const SETTINGS_KEY = "clipforge-settings-v2";
export const DRAFT_KEY = "clipforge-draft-v2";
export const WORKSPACE_KEY = "clipforge-workspace-v1";
export { VALID_ID } from "./validation";
export type HistoryItem = { id: string; kind: string; label: string; status: string; at: number; parent?: string };
export type Draft = EditorState & { version: 2; jobId: string; analysisJobId: string; renderJobId: string; projectId?: string; projectName?: string; projectNotes?: string; workspace?: string; url?: string; mode?: "url" | "upload"; fileName?: string };

export function readStorage(key: string): unknown {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) : null; }
  catch { return null; }
}
export function writeStorage(key: string, value: unknown): boolean {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch { return false; }
}
export function historyItems(value: unknown): HistoryItem[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is HistoryItem => Boolean(item) && typeof item.id === "string" && VALID_ID.test(item.id)
    && typeof item.kind === "string" && typeof item.label === "string" && typeof item.status === "string"
    && Number.isFinite(item.at)).slice(0, 30);
}
export function renderSettings(value: unknown): RenderSettings {
  const result = { ...DEFAULT_RENDER, durations: [...DEFAULT_RENDER.durations] };
  if (!value || typeof value !== "object" || Array.isArray(value)) return result;
  const record = value as Record<string, unknown>;
  for (const key of ["captions", "bgm", "duck", "face_crop", "grade", "hook_zoom"] as const) {
    if (typeof record[key] === "boolean") result[key] = record[key];
  }
  if (["9:16", "1:1", "16:9"].includes(String(record.aspect))) result.aspect = record.aspect as RenderSettings["aspect"];
  if (["default", "karaoke", "clean", "bold", "bengali", "hindi"].includes(String(record.caption_style))) result.caption_style = record.caption_style as RenderSettings["caption_style"];
  if (["", "shorts", "reels", "tiktok", "square", "youtube", "instagram"].includes(String(record.platform))) result.platform = String(record.platform);
  if (["exact", "target"].includes(String(record.render_mode))) result.render_mode = record.render_mode as RenderSettings["render_mode"];
  if (Array.isArray(record.durations)) {
    const durations = record.durations.filter((n) => Number.isInteger(n) && n >= 5 && n <= 180).slice(0, 20);
    if (durations.length) result.durations = [...new Set(durations)].sort((a, b) => a - b);
  }
  for (const key of ["padding", "bgm_volume"] as const) {
    const n = record[key];
    if (typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= (key === "padding" ? 5 : 1)) result[key] = n;
  }
  return result;
}
export function editorState(value: unknown, length: number): EditorState | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Partial<EditorState>;
  if (!Array.isArray(record.selected) || !Array.isArray(record.trims) || record.selected.length !== length || record.trims.length !== length) return undefined;
  if (!record.selected.every((item) => typeof item === "boolean")) return undefined;
  if (!record.trims.every((trim) => trim && Number.isFinite(trim.start) && Number.isFinite(trim.end)
    && trim.start >= 0 && trim.end > trim.start && trim.end - trim.start <= 180)) return undefined;
  return { selected: [...record.selected], trims: record.trims.map((trim) => ({ start: trim.start, end: trim.end })) };
}
export function loadWorkspace(): string {
  const value = readStorage(WORKSPACE_KEY);
  return typeof value === "string" && VALID_ID.test(value) ? value : "local";
}
export function formatTime(value: number): string {
  const seconds = Math.max(0, Math.round(value));
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
  return `${h ? `${h.toString().padStart(2, "0")}:` : ""}${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
