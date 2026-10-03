import { forward, jobId, proxyError } from "../_worker";
export const runtime = "nodejs";

export async function GET(req: Request) {
  try {
    return forward(req, `/jobs/${jobId(req)}`, { method: "GET" });
  } catch (error) { return proxyError(error); }
}
