import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import client from "../api/client";
import IndexStatusBadge from "../components/IndexStatusBadge.jsx";

export default function RepositoryDetail() {
  const { repositoryId } = useParams();
  const [repo, setRepo] = useState(null);

  useEffect(() => {
    let interval;
    async function load() {
      const res = await client.get(`/repositories/${repositoryId}`);
      setRepo(res.data);
    }
    load();
    interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [repositoryId]);

  if (!repo) return <main className="p-10 text-slate-400">Loading…</main>;

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link to={`/projects/${repo.project_id}`} className="text-sm text-slate-400 hover:text-slate-200">
        ← Back to project
      </Link>

      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900 p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-100">
            {repo.github_url.replace("https://github.com/", "")}
          </h1>
          <IndexStatusBadge status={repo.index_status} />
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Branch</dt>
            <dd className="text-slate-200">{repo.branch}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Commit</dt>
            <dd className="text-slate-200">{repo.commit_sha?.slice(0, 8) ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Primary language</dt>
            <dd className="text-slate-200">{repo.primary_language ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Indexed chunks</dt>
            <dd className="text-slate-200">{repo.chunk_count}</dd>
          </div>
        </dl>

        {repo.index_status === "completed" && (
          <Link
            to={`/repositories/${repo.id}/chat`}
            className="mt-6 inline-block rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition"
          >
            Ask this codebase →
          </Link>
        )}
        {repo.index_status === "indexing" && (
          <p className="mt-6 text-sm text-blue-300">Indexing in progress — this page auto-refreshes.</p>
        )}
        {repo.index_status === "failed" && (
          <p className="mt-6 text-sm text-red-400">Indexing failed. Try re-indexing from the project page.</p>
        )}
      </div>
    </main>
  );
}
