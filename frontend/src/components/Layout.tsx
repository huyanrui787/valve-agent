import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchHealth } from "../api/client";
import type { Health } from "../types";

export function Layout() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>阀门智能体</h1>
        <p className="sub">标书 · 报价 · 知识检索</p>
        <nav className="nav">
          <NavLink to="/" end>
            智能报价
          </NavLink>
          <NavLink to="/bid">标书智能体</NavLink>
          <NavLink to="/projects">我的标书</NavLink>
          <NavLink to="/rag">知识检索</NavLink>
        </nav>
        <div className="status-pill">
          API:{" "}
          {health ? (
            <>
              <strong>{health.status}</strong> · {health.llm}
            </>
          ) : (
            "未连接 — 请先启动 valve-api"
          )}
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
