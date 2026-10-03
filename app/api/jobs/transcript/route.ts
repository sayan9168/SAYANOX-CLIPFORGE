import { forwardFile, jobId, proxyError, ProxyError } from "../_worker";
export const runtime = "nodejs";

export async function GET(req: Request) {
  try {
    const job = jobId(req);
    const format = new URL(req.url).searchParams.get("format") || "srt";
    if (!["srt", "vtt", "txt", "json"].includes(format)) throw new ProxyError("Invalid transcript format.", 400);
    return forwardFile(req, `/jobs/${job}/transcript?format=${format}`, `transcript-${job.slice(0, 8)}.${format}`, true);
  } catch (error) { return proxyError(error); }
}
