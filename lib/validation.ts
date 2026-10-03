// Absolute end, so IDs cannot contain trailing line breaks.
export const VALID_ID = /^[A-Za-z0-9_-]{1,64}(?![\s\S])/;

export type AnalysisOptions = { min_seconds: number; max_seconds: number; limit: number };
export const DEFAULT_ANALYSIS: AnalysisOptions = { min_seconds: 15, max_seconds: 90, limit: 8 };
export const MEDIA_EXTENSIONS = /\.(mp4|mov|mkv|webm|avi|m4v|mts|mp3|wav|m4a|aac|flac|ogg)$/i;

export function youtubeUrls(value: unknown): string[] {
  const text = Array.isArray(value) ? value.join("\n") : typeof value === "string" ? value : "";
  const urls = [...new Set(text.split(/[\n,]+/).map((url) => url.trim()).filter(Boolean))];
  if (!urls.length) throw new Error("Enter one or more YouTube video URLs.");
  if (urls.length > 5) throw new Error("Submit at most 5 videos per batch.");
  for (const raw of urls) {
    let valid = false;
    try {
      const url = new URL(raw);
      const hosts = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"];
      if (["http:", "https:"].includes(url.protocol) && hosts.includes(url.hostname) && !url.username && !url.password && ["", "80", "443"].includes(url.port)) {
        const id = url.hostname.endsWith("youtu.be") ? url.pathname.replace(/^\/+|\/+$/g, "")
          : url.pathname.replace(/\/$/, "") === "/watch" ? url.searchParams.get("v") || ""
          : /^\/(shorts|live|embed)\/([A-Za-z0-9_-]+)\/?$/.exec(url.pathname)?.[2] || "";
        valid = VALID_ID.test(id);
      }
    } catch { /* invalid URL */ }
    if (!valid) throw new Error(`Invalid YouTube video URL: ${raw.slice(0, 160)}`);
  }
  return urls;
}

export function analysisOptions(input: Record<string, unknown>): AnalysisOptions {
  const result = { ...DEFAULT_ANALYSIS };
  for (const key of ["min_seconds", "max_seconds", "limit"] as const) {
    if (input[key] === undefined) continue;
    const raw = input[key];
    if ((typeof raw !== "number" && typeof raw !== "string") || raw === "") throw new Error(`${key} must be numeric.`);
    const value = Number(raw);
    if (!Number.isFinite(value)) throw new Error(`${key} must be a finite number.`);
    result[key] = value;
  }
  if (result.min_seconds < 5 || result.max_seconds > 180 || result.max_seconds < result.min_seconds) {
    throw new Error("Require 5 ≤ minimum length ≤ maximum length ≤ 180 seconds.");
  }
  if (!Number.isInteger(result.limit) || result.limit < 1 || result.limit > 20) throw new Error("Highlight count must be 1–20.");
  return result;
}

export function allowedArtifact(path: string): boolean {
  return !path.includes("..") && !/[\x00-\x1f\x7f]/.test(path) && [
    /^clips\/[A-Za-z0-9][A-Za-z0-9._-]*\.(mp4|webm|jpg|jpeg|png|srt|vtt)$/i,
    /^source\.(mp4|mov|mkv|webm|avi|m4v|mts|mp3|wav|m4a|aac|flac|ogg)$/i,
    /^(energy|render|transcript)\.json$|^captions\.srt$/i,
  ].some((pattern) => pattern.test(path));
}

export function validateUpload(file: { name: string; size: number }, maximumMb = 2048): void {
  if (!MEDIA_EXTENSIONS.test(file.name)) throw new Error("Choose a supported video or audio file (MP4, MOV, MKV, WebM, MP3, WAV…).");
  if (!file.size) throw new Error("The selected file is empty.");
  if (file.size > maximumMb * 1024 * 1024) throw new Error(`File exceeds the worker's ${maximumMb} MB upload limit.`);
}
