import { createContext, useContext, useEffect, useState } from "react";
import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("codelens_access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    client
      .get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(email, password) {
    const res = await client.post("/auth/login", { email, password });
    localStorage.setItem("codelens_access_token", res.data.access_token);
    localStorage.setItem("codelens_refresh_token", res.data.refresh_token);
    const me = await client.get("/auth/me");
    setUser(me.data);
  }

  async function register(email, password, fullName) {
    await client.post("/auth/register", { email, password, full_name: fullName });
    await login(email, password);
  }

  async function logout() {
    try {
      await client.post("/auth/logout");
    } finally {
      localStorage.removeItem("codelens_access_token");
      localStorage.removeItem("codelens_refresh_token");
      setUser(null);
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
