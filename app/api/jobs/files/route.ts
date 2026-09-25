import { unavailable, workerBase, workerHeaders } from "../_worker";
export const runtime = "nodejs";

/* GET /api/jobs/files?job=<id>&path=clips/clip-01-vertical.mp4
   -> streams the generated clip from the worker (preview + download). */
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const job = q.get("job") || "";
  const path = q.get("path") || "";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(job)) {
    return Response.json({ error: "Invalid job id." }, { status: 400 });
  }
  // only allow files under clips/ — never expose params/job metadata here
  if (!/^clips\/[A-Za-z0-9._-]+\.mp4$/.test(path)) {
    return Response.json({ error: "Invalid file path." }, { status: 400 });
  }
  const base = workerBase();
  if (!base) return unavailable();
  let r: Response;
  try {
    r = await fetch(`${base}/jobs/${job}/files/${encodeURIComponent(path)}`, {
      headers: workerHeaders(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "Worker is unreachable." }, { status: 502 });
  }
  if (!r.ok || !r.body) {
    const data = await r.json().catch(() => ({ error: "File not found." }));
    return Response.json(data, { status: r.status || 502 });
  }
  return new Response(r.body, {
    status: 200,
    headers: {
      "Content-Type": r.headers.get("Content-Type") || "video/mp4",
      "Content-Length": r.headers.get("Content-Length") || "",
      "Content-Disposition": `inline; filename="${path.split("/").pop()}"`,
      "Cache-Control": "public, max-age=3600",
      "Accept-Ranges": "bytes",
    },
  });
}
