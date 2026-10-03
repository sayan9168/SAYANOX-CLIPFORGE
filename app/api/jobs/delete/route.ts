import { forward, jobId, proxyError } from "../_worker";
export const runtime = "nodejs";

export async function DELETE(req: Request) {
  try {
    return forward(req, `/jobs/${jobId(req)}`, { method: "DELETE" });
  } catch (error) { return proxyError(error); }
}
