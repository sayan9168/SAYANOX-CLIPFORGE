import { unavailable, workerBase, workerHeaders } from "../_worker";
export const runtime = "nodejs";

/* POST /api/jobs/upload — multipart proxy to worker /jobs/upload */
export async function POST(req: Request) {
  const base = workerBase();
  if (!base) return unavailable();
  const form = await req.formData();
  let r: Response;
  try {
    r = await fetch(base + "/jobs/upload", {
      method: "POST",
      headers: workerHeaders(req),
      body: form,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "Worker is unreachable." }, { status: 502 });
  }
  const data = await r.json().catch(() => ({ error: "Worker returned invalid JSON." }));
  return Response.json(data, { status: r.status });
}
