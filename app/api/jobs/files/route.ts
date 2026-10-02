import { allowedArtifact } from "../../../../lib/validation";
import { forwardFile, jobId, proxyError, ProxyError } from "../_worker";
export const runtime = "nodejs";

export async function GET(req: Request) {
  try {
    const job = jobId(req);
    const query = new URL(req.url).searchParams;
    const path = query.get("path") || "";
    if (!allowedArtifact(path)) throw new ProxyError("Invalid file path.", 400);
    const encoded = path.split("/").map(encodeURIComponent).join("/");
    return forwardFile(req, `/jobs/${job}/files/${encoded}`, path.split("/").pop() || "clip.mp4", query.get("download") === "1");
  } catch (error) { return proxyError(error); }
}
