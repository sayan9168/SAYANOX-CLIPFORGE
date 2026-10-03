import assert from "node:assert/strict";
import { test } from "node:test";
import { allowedArtifact, analysisOptions, validateUpload, youtubeUrls } from "../lib/validation";
import { editorState, formatTime, historyItems, renderSettings } from "../lib/storage";
import { apiMessage } from "../lib/api";

test("YouTube batches are validated, bounded and deduplicated", () => {
  assert.deepEqual(youtubeUrls("https://youtu.be/abc,https://youtu.be/abc\nhttps://m.youtube.com/shorts/xyz"), ["https://youtu.be/abc", "https://m.youtube.com/shorts/xyz"]);
  for (const value of ["", "https://youtube.com.evil.example/watch?v=x", "https://user@youtube.com/watch?v=x", "file:///watch?v=x", "https://youtube.com/playlist?list=x", "https://youtube.com:8080/watch?v=x"]) assert.throws(() => youtubeUrls(value));
  assert.throws(() => youtubeUrls(Array.from({ length: 6 }, (_, index) => `https://youtu.be/x${index}`)), /at most 5/);
});

test("Analysis options reject invalid or non-finite controls", () => {
  assert.deepEqual(analysisOptions({}), { min_seconds: 15, max_seconds: 90, limit: 8 });
  assert.equal(analysisOptions({ min_seconds: "5", max_seconds: 10, limit: 2 }).min_seconds, 5);
  for (const value of [{ min_seconds: NaN }, { max_seconds: Infinity }, { min_seconds: 4 }, { max_seconds: 181 }, { min_seconds: 50, max_seconds: 30 }, { limit: 2.5 }, { limit: 21 }, { min_seconds: null }, { min_seconds: "" }]) assert.throws(() => analysisOptions(value));
});

test("Only intended artifacts are public through the file proxy", () => {
  for (const path of ["source.mov", "source.mkv", "source.wav", "energy.json", "render.json", "clips/clip-01-vertical.srt", "clips/clip-01-vertical.vtt", "clips/clip-01-vertical.mp4"]) assert.equal(allowedArtifact(path), true, path);
  for (const path of ["../job-x/source.mp4", "clips/../../params.json", "job.json", "params.json", ".env", "clips/.secret.mp4", "clips/a..mp4", "clips/clip.svg", "source.mp4/../params.json"]) assert.equal(allowedArtifact(path), false, path);
});

test("Upload validation reports size, type and empty-file errors before sending", () => {
  validateUpload({ name: "authorized.MP4", size: 100 }, 1);
  validateUpload({ name: "recording.wav", size: 100 });
  assert.throws(() => validateUpload({ name: "empty.mp4", size: 0 }), /empty/);
  assert.throws(() => validateUpload({ name: "bad.exe", size: 10 }), /supported/);
  assert.throws(() => validateUpload({ name: "large.mp4", size: 1024 ** 2 + 1 }, 1), /limit/);
});

test("Corrupt preferences and history cannot break hydration", () => {
  assert.deepEqual(historyItems({ nope: true }), []);
  assert.deepEqual(historyItems([null, { id: "../bad" }, { id: "valid123", kind: "render", label: "Output", status: "completed", at: 1 }]).map((item) => item.id), ["valid123"]);
  const settings = renderSettings({ aspect: "wrong", durations: [NaN, 0, 500, 22, 22], grade: "yes", bgm: true, bgm_volume: Infinity });
  assert.equal(settings.aspect, "9:16"); assert.equal(settings.grade, false); assert.equal(settings.bgm, true); assert.equal(settings.bgm_volume, 0.18); assert.deepEqual(settings.durations, [22]);
  assert.equal(editorState({ selected: [true], trims: [{ start: -1, end: 2 }] }, 1), undefined);
  assert.equal(editorState({ selected: [true], trims: [{ start: 0, end: 2 }] }, 2), undefined);
  assert.deepEqual(editorState({ selected: [false], trims: [{ start: 0.5, end: 2.5 }] }, 1), { selected: [false], trims: [{ start: 0.5, end: 2.5 }] });
});

test("Time formatting carries seconds into minutes/hours", () => {
  assert.equal(formatTime(59.9), "01:00"); assert.equal(formatTime(3599.9), "01:00:00"); assert.equal(formatTime(-2), "00:00");
});

test("API validation details become readable text instead of object strings", () => {
  assert.equal(apiMessage({ detail: [{ loc: ["body", "duration"], msg: "Invalid duration" }] }), "body.duration: Invalid duration");
  assert.equal(apiMessage({ error: "Storage full" }), "Storage full");
});

test("IDs and artifact paths reject trailing control characters", async () => {
  const { VALID_ID } = await import("../lib/validation");
  for (const id of ["job123\n", "job123\r", "job123\u0000", "a/b", ""]) assert.equal(VALID_ID.test(id), false);
  assert.equal(VALID_ID.test("job_123-ok"), true);
  assert.equal(allowedArtifact("source.mp4\n"), false);
  assert.throws(() => youtubeUrls("https://youtube.com/watch?v=valid%0A"), /Invalid/);
});
