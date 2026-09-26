import { NextResponse } from "next/server";
export const runtime = "nodejs";
const yt = /^https?:\/\/(www\.)?(youtube\.com|youtu\.be)\//i;

export async function POST(req: Request) {
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }
  const raw = String(body?.url || body?.urls || "").trim();
  const urls = raw
    .split(/[\n,]+/)
    .map((u: string) => u.trim())
    .filter(Boolean);
  if (!urls.length) {
    return NextResponse.json({ error: "Enter one or more YouTube URLs." }, { status: 400 });
  }
  for (const url of urls) {
    if (!yt.test(url)) {
      return NextResponse.json({ error: `Invalid YouTube URL: ${url}` }, { status: 400 });
    }
  }
  const base = (process.env.WORKER_API_URL || "").replace(/\/+$/, "");
  if (!base) {
    return NextResponse.json(
      {
        error:
          "Worker is not configured. Set WORKER_API_URL (example: http://127.0.0.1:8000) and start the FastAPI worker. Demo mode is disabled.",
      },
      { status: 503 },
    );
  }
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (process.env.WORKER_API_TOKEN) headers.Authorization = `Bearer ${process.env.WORKER_API_TOKEN}`;

  const jobs: { url: string; job_id?: string; error?: string }[] = [];
  for (const url of urls) {
    const payload: Record<string, unknown> = { url };
    for (const k of ["min_seconds", "max_seconds", "limit"]) {
      if (body?.[k] !== undefined && body?.[k] !== null && body?.[k] !== "") payload[k] = Number(body[k]);
    }
    try {
      const r = await fetch(base + "/jobs/youtube", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        cache: "no-store",
      });
      const data = await r.json().catch(() => ({ error: "Worker returned invalid JSON." }));
      if (!r.ok) jobs.push({ url, error: data.detail || data.error || "rejected" });
      else jobs.push({ url, job_id: data.job_id });
    } catch {
      jobs.push({ url, error: "Worker is unreachable." });
    }
  }
  const first = jobs.find((j) => j.job_id);
  if (!first?.job_id) {
    return NextResponse.json(
      { error: jobs[0]?.error || "Worker is unreachable. Is it running?", jobs },
      { status: 502 },
    );
  }
  return NextResponse.json({
    mode: "worker",
    job_id: first.job_id,
    jobs,
    batch: jobs.length > 1,
  });
}
