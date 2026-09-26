import { unavailable, workerBase, workerHeaders } from "../_worker";
export const runtime = "nodejs";

/* GET /api/jobs/zip?job=<id> — stream ZIP of all clips */
export async function GET(req: Request) {
  const job = new URL(req.url).searchParams.get("job") || "";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(job)) {
    return Response.json({ error: "Invalid job id." }, { status: 400 });
  }
  const base = workerBase();
  if (!base) return unavailable();
  let r: Response;
  try {
    r = await fetch(`${base}/jobs/${job}/zip`, {
      headers: workerHeaders(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "Worker is unreachable." }, { status: 502 });
  }
  if (!r.ok || !r.body) {
    const data = await r.json().catch(() => ({ error: "ZIP not available." }));
    return Response.json(data, { status: r.status || 502 });
  }
  return new Response(r.body, {
    status: 200,
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": r.headers.get("Content-Disposition")
        || `attachment; filename="clipforge-${job.slice(0, 8)}.zip"`,
      "Cache-Control": "no-store",
    },
  });
}
