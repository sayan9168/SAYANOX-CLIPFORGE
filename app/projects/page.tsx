"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, FolderOpen, Loader2, RefreshCw, Save, Trash2 } from "lucide-react";
import { requestJson } from "../../lib/api";
import { VALID_ID, WORKSPACE_KEY, loadWorkspace, writeStorage } from "../../lib/storage";
import type { Project } from "../../lib/types";
import { SiteNav } from "../components/SiteNav";
import { WorkerStatus } from "../components/WorkerStatus";

export default function ProjectsPage() {
  const [items, setItems] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState("");
  const [workspace, setWorkspace] = useState("local");
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => { setWorkspace(loadWorkspace()); setReady(true); }, []);
  useEffect(() => {
    if (!ready) return;
    if (!VALID_ID.test(workspace)) { setError("Workspace keys use 1–64 letters, numbers, underscores or hyphens."); setLoading(false); return; }
    writeStorage(WORKSPACE_KEY, workspace);
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      requestJson<{ projects: Project[] }>("/api/projects", { headers: { "x-clipforge-user": workspace }, signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) { setItems(data.projects || []); setError(""); } })
        .catch((failure) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Could not load projects."); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [ready, workspace, revision]);
  async function save() {
    if (!name.trim() || !VALID_ID.test(workspace) || jobId && !VALID_ID.test(jobId)) { setError("Enter a project name, a valid workspace key and (optionally) a valid job ID."); return; }
    setPending("save"); setError("");
    try {
      const project = await requestJson<Project>("/api/projects", { method: "POST", headers: { "content-type": "application/json", "x-clipforge-user": workspace }, body: JSON.stringify({ name: name.trim(), job_id: jobId || undefined }) });
      setMessage(`“${project.name}” saved. For trims and render settings, save directly from the studio.`); setName(""); setJobId(""); setRevision((value) => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not save project."); }
    finally { setPending(""); }
  }
  async function remove(id: string) {
    if (!window.confirm("Delete this project snapshot? Its worker jobs and media files will not be deleted.")) return;
    setPending(id); setError("");
    try { await requestJson(`/api/projects?id=${id}`, { method: "DELETE", headers: { "x-clipforge-user": workspace } }); setMessage("Project deleted; media jobs were kept."); setRevision((value) => value + 1); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not delete project."); }
    finally { setPending(""); }
  }
  function exportProject(project: Project) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(project, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `clipforge-project-${project.id}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <main><SiteNav page="projects" /><header className="pageHeader"><span className="eyebrow">SAVED ON YOUR WORKER</span><h1>Your edits, organized.</h1><p>Save clip selections, precise trims, notes and export settings. Reopen any snapshot in the studio.</p></header><WorkerStatus />
    <section className="projectWorkspace"><label>Workspace key<input aria-label="Workspace key" value={workspace} maxLength={64} onChange={(event) => setWorkspace(event.target.value)} /></label><button type="button" className="chip" disabled={loading} onClick={() => setRevision((value) => value + 1)}><RefreshCw size={13} /> Refresh</button><p>Keys organize your projects, not user authentication. All media still follows the worker retention policy.</p></section>
    <details className="projectCreate"><summary>Create a project bookmark</summary><div className="projectFields"><label>Name<input aria-label="New project name" value={name} maxLength={80} onChange={(event) => setName(event.target.value)} placeholder="My next video" /></label><label>Analyze job ID (optional)<input aria-label="Project job ID" value={jobId} maxLength={64} onChange={(event) => setJobId(event.target.value)} placeholder="Paste a worker job ID" /></label><button type="button" className="renderBtn" disabled={Boolean(pending)} onClick={save}><Save size={13} /> Save bookmark</button></div></details>
    {error && <p className="error" role="alert">{error}</p>}{message && <p className="note" role="status">{message}</p>}{loading && <p className="hint"><Loader2 size={14} className="spin" /> Loading your workspace…</p>}
    {!loading && !error && !items.length && <div className="emptyState"><FolderOpen size={28} /><h3>Make room for your next idea.</h3><p>Analyze a video and save the edit from the studio, or create a bookmark above.</p><Link href="/" className="dl">Open studio</Link></div>}
    {!loading && !error && <div className="projectGrid">{items.map((project) => <article className="projectCard" key={project.id}><span className="eyebrow">{project.settings?.aspect || "Project"} · {project.settings?.caption_style || "default"}</span><h2>{project.name}</h2><p>{project.notes || "No notes yet."}</p><small>Updated {new Date(project.updated_at * 1000).toLocaleString()}<br />Job {project.job_id?.slice(0, 8) || "not linked"} · {project.editor?.selected.filter(Boolean).length || 0} picks</small><div className="projectCardActions"><Link href={`/?project=${project.id}`} className="dl">Open edit</Link><button type="button" className="chip" onClick={() => exportProject(project)} aria-label={`Export ${project.name}`}><Download size={13} /> JSON</button><button type="button" className="chip" disabled={Boolean(pending)} onClick={() => remove(project.id)} aria-label={`Delete ${project.name}`}><Trash2 size={13} /></button></div></article>)}</div>}
  </main>;
}
