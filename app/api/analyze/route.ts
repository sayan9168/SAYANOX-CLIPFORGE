import { analysisOptions, youtubeUrls } from "../../../lib/validation";
import { errorMessage, forward, proxyError, readJson } from "../jobs/_worker";
export const runtime = "nodejs";

export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try { body = await readJson(req); }
  catch (error) { return proxyError(error); }
  let urls: string[];
  let options;
  try { urls = youtubeUrls(body.url ?? body.urls); options = analysisOptions(body); }
  catch (error) { return Response.json({ error: error instanceof Error ? error.message : "Invalid request." }, { status: 400 }); }
  const jobs: { url: string; job_id?: string; error?: string }[] = [];
  let rejectedStatus = 502;
  for (const url of urls) {
    const response = await forward(req, "/jobs/youtube", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url, ...options }),
    });
    const data = await response.json();
    if (!response.ok) { rejectedStatus = response.status; jobs.push({ url, error: errorMessage(data) }); }
    else if (typeof data.job_id === "string") jobs.push({ url, job_id: data.job_id });
    else { rejectedStatus = 502; jobs.push({ url, error: "Worker did not return a job ID." }); }
  }
  const first = jobs.find((job) => job.job_id);
  if (!first) return Response.json({ error: jobs[0]?.error || "Could not start analysis.", jobs }, { status: rejectedStatus });
  return Response.json({ mode: "worker", job_id: first.job_id, jobs, batch: jobs.length > 1 });
}
