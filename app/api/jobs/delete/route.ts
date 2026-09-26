import { forward } from "../_worker";
export const runtime = "nodejs";

/* DELETE /api/jobs/delete?job=<id> */
export async function DELETE(req: Request) {
  const job = new URL(req.url).searchParams.get("job") || "";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(job)) {
    return Response.json({ error: "Invalid job id." }, { status: 400 });
  }
  return forward(req, `/jobs/${job}`, { method: "DELETE" });
}
