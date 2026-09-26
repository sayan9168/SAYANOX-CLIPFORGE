import { forward } from "../_worker";
export const runtime = "nodejs";

export async function GET(req: Request) {
  const r = await forward(req, "/jobs", { method: "GET" });
  if (r.status !== 404) return r;
  // Addon route may not be mounted yet; surface a clear empty list.
  return Response.json({ jobs: [], note: "Worker job list unavailable until worker restart." }, { status: 200 });
}
