const STYLES = {
  pending: "bg-slate-700 text-slate-300",
  queued: "bg-amber-900/50 text-amber-300",
  indexing: "bg-blue-900/50 text-blue-300 animate-pulse",
  completed: "bg-emerald-900/50 text-emerald-300",
  failed: "bg-red-900/50 text-red-300",
};

export default function IndexStatusBadge({ status }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status] ?? STYLES.pending}`}>
      {status}
    </span>
  );
}
