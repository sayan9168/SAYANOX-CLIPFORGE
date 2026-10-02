import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { forward, forwardJson, forwardUpload, workerHeaders } from "../app/api/jobs/_worker";
import { GET as getFile } from "../app/api/jobs/files/route";
import { GET as getProjects, DELETE as deleteProject } from "../app/api/projects/route";
import { POST as analyze } from "../app/api/analyze/route";
import { GET as health } from "../app/api/health/route";

const previous = { base: process.env.WORKER_API_URL, token: process.env.WORKER_API_TOKEN };
beforeEach(() => { process.env.WORKER_API_URL = "http://worker.test"; process.env.WORKER_API_TOKEN = "test-proxy-token"; });
afterEach(() => {
  mock.restoreAll();
  if (previous.base === undefined) delete process.env.WORKER_API_URL; else process.env.WORKER_API_URL = previous.base;
  if (previous.token === undefined) delete process.env.WORKER_API_TOKEN; else process.env.WORKER_API_TOKEN = previous.token;
});
const req = (url = "http://web.test/api/test") => new Request(url);

test("Proxy forwards the workspace namespace and server-side token", async () => {
  const request = new Request("http://web.test/api/projects", { headers: { "x-clipforge-user": "alpha", authorization: "Bearer attacker" } });
  assert.equal(workerHeaders(request).get("authorization"), "Bearer test-proxy-token");
  mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.equal(url, "http://worker.test/projects");
    assert.equal(new Headers(init.headers).get("x-clipforge-user"), "alpha");
    assert.equal(new Headers(init.headers).get("authorization"), "Bearer test-proxy-token");
    return Response.json({ projects: [] });
  });
  const response = await getProjects(request);
  assert.equal(response.status, 200);
  assert.equal(JSON.stringify(await response.json()).includes("test-proxy-token"), false);
});

test("Missing worker configuration is an explicit 503, not demo success", async () => {
  delete process.env.WORKER_API_URL;
  assert.equal((await forward(req(), "/jobs")).status, 503);
  const response = await health(req());
  assert.deepEqual((await response.json()).worker, { configured: false, reachable: false });
});

test("Worker errors preserve statuses, validation details and Retry-After", async () => {
  mock.method(globalThis, "fetch", async () => Response.json({ detail: [{ loc: ["body", "start"], msg: "Must be positive" }] }, { status: 429, headers: { "Retry-After": "12" } }));
  const response = await forward(req(), "/jobs");
  assert.equal(response.status, 429); assert.equal(response.headers.get("retry-after"), "12");
  assert.equal((await response.json()).error, "body.start: Must be positive");
});

test("Network failures, timeouts and malformed worker responses are bounded errors", async () => {
  mock.method(globalThis, "fetch", async () => { throw new Error("offline"); });
  assert.equal((await forward(req(), "/jobs")).status, 502);
  mock.restoreAll();
  mock.method(globalThis, "fetch", async () => { throw new DOMException("timeout", "TimeoutError"); });
  assert.equal((await forward(req(), "/jobs")).status, 504);
  mock.restoreAll();
  mock.method(globalThis, "fetch", async () => new Response("not JSON"));
  assert.equal((await forward(req(), "/jobs")).status, 502);
});

test("File proxy supports seeking and never publicly caches private media", async () => {
  mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.equal(url, "http://worker.test/jobs/job123/files/clips/clip.mp4");
    assert.equal(new Headers(init.headers).get("range"), "bytes=2-4");
    return new Response("abc", { status: 206, headers: { "Content-Type": "video/mp4", "Content-Length": "3", "Content-Range": "bytes 2-4/100", "Accept-Ranges": "bytes" } });
  });
  const response = await getFile(new Request("http://web.test/api/jobs/files?job=job123&path=clips%2Fclip.mp4", { headers: { Range: "bytes=2-4" } }));
  assert.equal(response.status, 206); assert.equal(await response.text(), "abc");
  assert.equal(response.headers.get("content-range"), "bytes 2-4/100"); assert.equal(response.headers.get("content-length"), "3"); assert.equal(response.headers.get("cache-control"), "private, no-store");
});

test("Unsatisfiable ranges retain the worker's 416 and Content-Range", async () => {
  mock.method(globalThis, "fetch", async () => new Response("Bad range", { status: 416, headers: { "Content-Range": "*/100" } }));
  const response = await getFile(req("http://web.test/api/jobs/files?job=job123&path=source.mov"));
  assert.equal(response.status, 416); assert.equal(response.headers.get("content-range"), "*/100");
});

test("Artifact and project traversal are rejected before any fetch", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => { throw new Error("must not fetch"); });
  for (const path of ["../job123/source.mp4", "params.json", "job.json"]) assert.equal((await getFile(req(`http://web.test/api/jobs/files?job=job123&path=${encodeURIComponent(path)}`))).status, 400);
  assert.equal((await deleteProject(req("http://web.test/api/projects?id=..%2Fescape"))).status, 400);
  assert.equal(fetch.mock.callCount(), 0);
});

test("Malformed or oversized JSON never reaches the worker", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => { throw new Error("must not fetch"); });
  for (const body of ["[1,2]", "null", "broken"]) {
    assert.equal((await forwardJson(new Request("http://web.test/api/jobs/render", { method: "POST", body }), "/jobs/render")).status, 400);
  }
  assert.equal((await forwardJson(new Request("http://web.test/api/jobs/render", { method: "POST", body: JSON.stringify({ text: "x".repeat(140_000) }) }), "/jobs/render")).status, 413);
  assert.equal(fetch.mock.callCount(), 0);
});

test("Upload proxy streams multipart data without rebuilding or buffering it", async () => {
  const form = new FormData(); form.append("video", new File(["video bytes"], "clip.mp4"));
  const request = new Request("http://web.test/api/jobs/upload", { method: "POST", body: form });
  const contentType = request.headers.get("content-type");
  mock.method(globalThis, "fetch", async (url: string, init: RequestInit & { duplex: string }) => {
    assert.equal(url, "http://worker.test/jobs/upload"); assert.equal(init.duplex, "half"); assert.ok(init.body instanceof ReadableStream);
    assert.equal(new Headers(init.headers).get("content-type"), contentType);
    return Response.json({ job_id: "job123", status: "queued" });
  });
  assert.equal((await forwardUpload(request)).status, 200);
  assert.equal((await forwardUpload(new Request("http://web.test/api/jobs/upload", { method: "POST", body: "bad" }))).status, 400);
});

test("Analyze validates all URLs before creating any batch jobs", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => { throw new Error("must not fetch"); });
  const response = await analyze(new Request("http://web.test/api/analyze", { method: "POST", body: JSON.stringify({ urls: ["https://youtu.be/ok", "https://evil.test/no"] }) }));
  assert.equal(response.status, 400); assert.equal(fetch.mock.callCount(), 0);
});

test("Batch analysis returns partial success without hiding rejected videos", async () => {
  let index = 0;
  mock.method(globalThis, "fetch", async () => ++index === 1 ? Response.json({ job_id: "job123" }) : Response.json({ detail: "Queue full" }, { status: 503 }));
  const response = await analyze(new Request("http://web.test/api/analyze", { method: "POST", body: JSON.stringify({ urls: ["https://youtu.be/one", "https://youtu.be/two"] }) }));
  const data = await response.json();
  assert.equal(response.status, 200); assert.equal(data.job_id, "job123"); assert.equal(data.batch, true); assert.equal(data.jobs[1].error, "Queue full");
});

test("Health diagnostics detect a mismatched worker token before jobs are submitted", async () => {
  mock.method(globalThis, "fetch", async (url: string) => url.endsWith("/health")
    ? Response.json({ ok: true, ready: true, ffmpeg: true, ffprobe: true, auth_required: true })
    : Response.json({ error: "Invalid token" }, { status: 401 }));
  const response = await health(req());
  const data = await response.json();
  assert.equal(response.status, 200); assert.equal(data.worker.reachable, true); assert.equal(data.worker.ready, false);
  assert.match(data.worker.error, /same WORKER_API_TOKEN/);
});
