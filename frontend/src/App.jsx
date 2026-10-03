import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import ProjectDetail from "./pages/ProjectDetail.jsx";
import RepositoryDetail from "./pages/RepositoryDetail.jsx";
import Chat from "./pages/Chat.jsx";
import NavBar from "./components/NavBar.jsx";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <CenteredSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function CenteredSpinner() {
  return (
    <div className="flex h-screen items-center justify-center text-slate-400">
      Loading…
    </div>
  );
}

export default function App() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950">
      {user && <NavBar />}
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/projects/:projectId"
          element={
            <ProtectedRoute>
              <ProjectDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/repositories/:repositoryId"
          element={
            <ProtectedRoute>
              <RepositoryDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/repositories/:repositoryId/chat"
          element={
            <ProtectedRoute>
              <Chat />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
