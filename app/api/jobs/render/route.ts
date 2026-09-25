import { forward } from "../_worker";
export const runtime = "nodejs";

/* POST /api/jobs/render {parent_job, durations, ...} -> worker POST /jobs/render */
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid request." }, { status: 400 });
  }
  return forward(req, "/jobs/render", { method: "POST", body: JSON.stringify(body ?? {}) });
}
