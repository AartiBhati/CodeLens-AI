import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function NavBar() {
  const { user, logout } = useAuth();

  return (
    <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-center gap-2 font-semibold text-slate-100">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-brand-500" />
          CodeLens AI
        </Link>
        <div className="flex items-center gap-4 text-sm text-slate-400">
          <span>{user?.email}</span>
          <button
            onClick={logout}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-slate-200 hover:bg-slate-800 transition"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
