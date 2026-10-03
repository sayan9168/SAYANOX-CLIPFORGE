import type { AnalysisOptions } from "./validation";
import type { SocialPack } from "../app/components/SocialCaption";

export type Aspect = "9:16" | "1:1" | "16:9";
export type CaptionStyle = "default" | "karaoke" | "clean" | "bold" | "bengali" | "hindi";
export type Trim = { start: number; end: number };
export type Highlight = Trim & SocialPack & {
  score: number; title?: string; reason?: string; text?: string;
  packs?: Record<string, SocialPack>;
  languages?: Record<string, Record<string, SocialPack>>;
  signals?: Record<string, number | undefined>;
};
export type RenderClip = Trim & {
  file: string; duration: number; target: number; score: number | null;
  aspect?: Aspect; vertical: boolean; captions: boolean; bgm?: boolean;
  bytes: number; download: string; thumbnail?: string | null;
  subtitles?: { srt?: string; vtt?: string };
};
export type JobState = "preparing" | "queued" | "processing" | "cancelling" | "completed" | "failed" | "cancelled";
export const TERMINAL_STATES: JobState[] = ["completed", "failed", "cancelled"];
export type JobResult = {
  duration?: number; engine?: string; language?: string; source_file?: string;
  has_video?: boolean; has_audio?: boolean; has_transcript?: boolean;
  transcript_segments?: number; scene_changes?: number; warnings?: string[];
  clips?: Highlight[] | RenderClip[];
};
export type JobStatus = {
  job_id: string; kind: "analyze" | "render"; status: JobState; stage?: string;
  label?: string; parent_job?: string; progress: number; attempts: number;
  max_attempts: number; error: string | null; result: JobResult | null;
  created_at?: number; updated_at?: number;
};
export type JobRow = Omit<JobStatus, "job_id" | "result"> & { id: string };
export type RenderSettings = {
  durations: number[]; aspect: Aspect; caption_style: CaptionStyle; captions: boolean;
  padding: number; bgm: boolean; duck: boolean; bgm_volume: number; face_crop: boolean;
  grade: boolean; hook_zoom: boolean; platform: string; render_mode: "exact" | "target";
};
export const DEFAULT_RENDER: RenderSettings = {
  durations: [30], aspect: "9:16", caption_style: "default", captions: true,
  padding: 0.5, bgm: false, duck: true, bgm_volume: 0.18, face_crop: true,
  grade: false, hook_zoom: false, platform: "", render_mode: "exact",
};
export type EditorState = { selected: boolean[]; trims: Trim[] };
export type Project = {
  id: string; name: string; job_id?: string | null; render_job_id?: string | null;
  url?: string; notes?: string; settings?: RenderSettings; analysis?: AnalysisOptions;
  editor?: EditorState; created_at?: number; updated_at: number;
};
export type WorkerHealth = {
  configured: boolean; reachable: boolean; ready?: boolean; version?: string;
  ffmpeg?: boolean; ffprobe?: boolean; yt_dlp?: boolean; youtube_enabled?: boolean;
  whisper_engine?: string; queue_jobs?: number; max_upload_mb?: number;
  storage_bytes?: number; max_storage_bytes?: number; concurrency?: number; error?: string;
};
