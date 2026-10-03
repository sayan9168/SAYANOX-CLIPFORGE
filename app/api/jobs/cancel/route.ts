import { forward, jobId, proxyError } from "../_worker";
export const runtime = "nodejs";

export async function POST(req: Request) {
  try {
    return forward(req, `/jobs/${jobId(req)}/cancel`, { method: "POST" });
  } catch (error) { return proxyError(error); }
}
