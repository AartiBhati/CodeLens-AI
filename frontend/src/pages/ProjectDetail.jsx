import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import client from "../api/client";
import IndexStatusBadge from "../components/IndexStatusBadge.jsx";

export default function ProjectDetail() {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [repos, setRepos] = useState([]);
  const [githubUrl, setGithubUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  async function loadAll() {
    const [projectRes, reposRes] = await Promise.all([
      client.get(`/projects/${projectId}`),
      client.get(`/projects/${projectId}/repositories`),
    ]);
    setProject(projectRes.data);
    setRepos(reposRes.data);
  }

  useEffect(() => {
    loadAll();
    // Poll periodically so index status updates without a manual refresh.
    const interval = setInterval(loadAll, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function handleConnect(e) {
    e.preventDefault();
    setError("");
    setConnecting(true);
    try {
      const res = await client.post(`/projects/${projectId}/repositories`, {
        github_url: githubUrl,
        branch,
      });
      await client.post(`/repositories/${res.data.id}/index`);
      setGithubUrl("");
      await loadAll();
    } catch (err) {
      setError(err.response?.data?.detail ?? "Could not connect repository");
    } finally {
      setConnecting(false);
    }
  }

  async function handleReindex(repoId) {
    await client.post(`/repositories/${repoId}/index`);
    await loadAll();
  }

  if (!project) return <main className="p-10 text-slate-400">Loading…</main>;

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link to="/" className="text-sm text-slate-400 hover:text-slate-200">
        ← Projects
      </Link>
      <h1 className="mt-2 text-2xl font-semibold text-slate-100">{project.name}</h1>
      {project.description && <p className="mt-1 text-slate-400">{project.description}</p>}

      <form onSubmit={handleConnect} className="mt-8 rounded-lg border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-3 text-sm font-medium text-slate-300">Connect a repository</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            required
            placeholder="https://github.com/org/repo"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            className="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
          />
          <input
            placeholder="branch"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none sm:w-32"
          />
          <button
            type="submit"
            disabled={connecting}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition"
          >
            {connecting ? "Connecting…" : "Connect & index"}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </form>

      <div className="mt-6 space-y-3">
        {repos.map((r) => (
          <div
            key={r.id}
            className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-4"
          >
            <div>
              <Link to={`/repositories/${r.id}`} className="font-medium text-slate-100 hover:text-brand-400">
                {r.github_url.replace("https://github.com/", "")}
              </Link>
              <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                <span>{r.branch}</span>
                {r.primary_language && <span>· {r.primary_language}</span>}
                <span>· {r.chunk_count} chunks</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <IndexStatusBadge status={r.index_status} />
              <button
                onClick={() => handleReindex(r.id)}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 transition"
              >
                Re-index
              </button>
              {r.index_status === "completed" && (
                <Link
                  to={`/repositories/${r.id}/chat`}
                  className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700 transition"
                >
                  Ask
                </Link>
              )}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
