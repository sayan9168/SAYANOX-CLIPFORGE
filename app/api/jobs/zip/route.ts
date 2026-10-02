import { forwardFile, jobId, proxyError } from "../_worker";
export const runtime = "nodejs";

export async function GET(req: Request) {
  try {
    const job = jobId(req);
    return forwardFile(req, `/jobs/${job}/zip`, `clipforge-${job.slice(0, 8)}.zip`, true);
  } catch (error) { return proxyError(error); }
}
