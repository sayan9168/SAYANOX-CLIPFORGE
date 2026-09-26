"use client";
import { useEffect, useState } from "react";

export default function ProjectsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [name, setName] = useState("My project");
  const [user, setUser] = useState("local");
  async function load() {
    const r = await fetch("/api/projects", { headers: { "x-clipforge-user": user } });
    const d = await r.json();
    setItems(d.projects || []);
  }
  useEffect(() => { load(); }, [user]);
  async function save() {
    await fetch("/api/projects", {
      method: "POST",
      headers: { "content-type": "application/json", "x-clipforge-user": user },
      body: JSON.stringify({ name }),
    });
    load();
  }
  return (
    <main>
      <h1>Saved projects</h1>
      <p className="sub">Stored on the worker volume. Account key is the user field (share it only with yourself).</p>
      <div className="inputRow">
        <input value={user} onChange={(e) => setUser(e.target.value)} placeholder="account key" />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="project name" />
        <button type="button" onClick={save}>Save</button>
      </div>
      <ul className="historyList">
        {items.map((p) => (
          <li key={p.id}><div><b>{p.name}</b><small>{p.id} · job {p.job_id || "—"}</small></div></li>
        ))}
      </ul>
    </main>
  );
}
