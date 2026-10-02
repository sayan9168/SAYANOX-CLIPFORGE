import { expect, test, type Page } from "@playwright/test";

async function health(page: Page, configured = false) {
  await page.route("**/api/health", (route) => route.fulfill({ json: { ok: true, worker: { configured, reachable: configured, ready: configured, whisper_engine: "srt-sidecar", max_upload_mb: 100, queue_jobs: 0, ffmpeg: true, ffprobe: true } } }));
}

test("Offline setup and invalid uploads are clear, including mobile layout", async ({ page }) => {
  await health(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Worker not configured", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Upload file", exact: true }).click();
  await page.locator('input[accept^=".mp4"]').setInputFiles({ name: "unsafe.exe", mimeType: "application/octet-stream", buffer: Buffer.from("bad") });
  await expect(page.locator("main .error[role=alert]")).toContainText("supported video or audio");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Every job, under control." })).toBeVisible();
});

test("Batch URLs and analysis limits are validated before submission", async ({ page }) => {
  await health(page, true);
  await page.goto("/");
  await page.getByLabel("YouTube video URLs").fill("https://evil.test/watch?v=x");
  await page.getByRole("button", { name: "Find clips" }).click();
  await expect(page.locator("main .error[role=alert]")).toContainText("Invalid YouTube");
  await page.getByLabel("YouTube video URLs").fill("https://youtu.be/valid");
  await page.getByText("Analysis controls", { exact: false }).click();
  await page.getByLabel("Minimum seconds").fill("70");
  await page.getByLabel("Maximum seconds").fill("20");
  await page.getByRole("button", { name: "Find clips" }).click();
  await expect(page.locator("main .error[role=alert]")).toContainText("minimum length");
});

test("Recoverable polling, exact trims and real render settings survive reload", async ({ page }) => {
  await health(page, true);
  const highlight = { start: 0, end: 20, score: 80, title: "A useful moment", text: "Here is why this matters!", reason: "Strong hook" };
  const completed = { job_id: "analysis123", kind: "analyze", label: "My video", status: "completed", progress: 100, attempts: 1, max_attempts: 3, error: null, result: { clips: [highlight], duration: 60, engine: "srt-sidecar", source_file: "source.mov", has_transcript: true, has_video: true, transcript_segments: 2 } };
  await page.route("**/api/analyze", (route) => route.fulfill({ json: { job_id: "analysis123", jobs: [{ url: "https://youtu.be/valid", job_id: "analysis123" }] } }));
  let requests = 0;
  await page.route("**/api/jobs/status?*", async (route) => {
    if (new URL(route.request().url()).searchParams.get("job") === "render123") return route.fulfill({ json: { ...completed, job_id: "render123", kind: "render", parent_job: "analysis123", result: { clips: [] } } });
    if (++requests === 1) return route.fulfill({ status: 502, json: { error: "Temporary network issue" } });
    return route.fulfill({ json: completed });
  });
  await page.route("**/api/jobs/files?*", (route) => route.fulfill({ json: [-30, -20, -15, -40] }));
  await page.goto("/");
  await page.getByLabel("YouTube video URLs").fill("https://youtu.be/valid");
  await page.getByRole("button", { name: "Find clips" }).click();
  await expect(page.getByText("Connection interrupted.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "A useful moment" })).toBeVisible();
  await page.getByLabel("Clip 1 in seconds").fill("2");
  await page.getByRole("button", { name: "Color grade", exact: true }).click();
  await page.getByRole("button", { name: "2s hook zoom", exact: true }).click();
  await page.getByLabel("Project name").fill("Careful launch edit");
  await page.getByLabel("Project notes").fill("Keep the useful detail.");
  await page.reload();
  await expect(page.getByLabel("Project name")).toHaveValue("Careful launch edit");
  await expect(page.getByLabel("Project notes")).toHaveValue("Keep the useful detail.");
  await expect(page.getByLabel("Clip 1 in seconds")).toHaveValue("2");
  await expect(page.getByRole("button", { name: "Color grade", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "2s hook zoom", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("link", { name: "VTT", exact: true })).toHaveAttribute("href", /format=vtt/);
  const payload = page.waitForRequest((request) => request.url().endsWith("/api/jobs/render") && request.method() === "POST");
  await page.route("**/api/jobs/render", (route) => route.fulfill({ json: { job_id: "render123" } }));
  await page.getByRole("button", { name: "Render 1 clip", exact: true }).click();
  const body = (await payload).postDataJSON();
  expect(body.grade).toBe(true); expect(body.hook_zoom).toBe(true); expect(body.render_mode).toBe("exact"); expect(body.highlights[0].start).toBe(2); expect(body.highlights[0].locked).toBe(true);
});

test("Project workspace forwarding and saved snapshots open without cross-talk", async ({ page }) => {
  await health(page, true);
  await page.addInitScript(() => localStorage.setItem("clipforge-workspace-v1", JSON.stringify("alpha")));
  await page.route("**/api/projects", (route) => {
    expect(route.request().headers()["x-clipforge-user"]).toBe("alpha");
    return route.fulfill({ json: { projects: [{ id: "project123", name: "Saved edit", job_id: "source123", notes: "A careful cut", updated_at: 1700000000, settings: { aspect: "1:1", caption_style: "bold" }, editor: { selected: [true], trims: [{ start: 1, end: 20 }] } }] } });
  });
  await page.goto("/projects");
  await expect(page.getByLabel("Workspace key")).toHaveValue("alpha");
  await expect(page.getByRole("heading", { name: "Saved edit" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open edit" })).toHaveAttribute("href", "/?project=project123");
});

test("A disabled YouTube worker directs users to uploads without queuing failed jobs", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { worker: { configured: true, reachable: true, ready: true, youtube_enabled: false, yt_dlp: false, max_upload_mb: 100 } } }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Find clips" })).toBeDisabled();
  await page.getByRole("button", { name: "Upload a file instead" }).click();
  await expect(page.getByRole("button", { name: "Choose video file" })).toBeVisible();
});
