import { forward } from "../_worker";
export const runtime = "nodejs";

/* POST /api/jobs/youtube {url,...} -> worker POST /jobs/youtube -> {job_id,status} */
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid request." }, { status: 400 });
  }
  return forward(req, "/jobs/youtube", { method: "POST", body: JSON.stringify(body ?? {}) });
}
