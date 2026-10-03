import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";

export default function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  async function loadProjects() {
    setLoading(true);
    const res = await client.get("/projects");
    setProjects(res.data);
    setLoading(false);
  }

  useEffect(() => {
    loadProjects();
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    setCreating(true);
    try {
      await client.post("/projects", { name, description });
      setName("");
      setDescription("");
      setShowForm(false);
      await loadProjects();
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Projects</h1>
          <p className="text-sm text-slate-400">Connect a GitHub repository and start asking questions.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition"
        >
          New project
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mb-8 rounded-lg border border-slate-800 bg-slate-900 p-5 space-y-3">
          <input
            required
            placeholder="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
          />
          <textarea
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
            rows={2}
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition"
          >
            {creating ? "Creating…" : "Create project"}
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : projects.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-800 p-10 text-center text-slate-400">
          No projects yet. Create one to connect your first repository.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/projects/${p.id}`}
              className="rounded-lg border border-slate-800 bg-slate-900 p-5 hover:border-brand-600 transition"
            >
              <h3 className="font-medium text-slate-100">{p.name}</h3>
              {p.description && <p className="mt-1 text-sm text-slate-400 line-clamp-2">{p.description}</p>}
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
