// Shared helpers for the three pages (plain ES modules, no build step).

export async function api(path, options = {}) {
  const init = { ...options, headers: { ...(options.headers || {}) } };
  if (init.body && typeof init.body !== "string") {
    init.body = JSON.stringify(init.body);
    init.headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, init);
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    const detail = data && data.detail;
    const message = Array.isArray(detail) ? detail.map((d) => d.msg).join("；") : detail || `請求失敗（${response.status}）`;
    throw new Error(message);
  }
  return data;
}

// Tiny element builder: h("p", {class: "x", onclick}, "text", child)
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export const TOOL_NAMES = { github: "GitHub", notion: "Notion", discord: "Discord", decision: "決策紀錄" };

export function goUrl(url, params = {}) {
  const query = new URLSearchParams({ url });
  for (const [key, value] of Object.entries(params)) if (value !== null && value !== undefined) query.set(key, value);
  return `/go?${query}`;
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// Top-right status: document count, the AI model in use (or a warning if none is set up), and a button to
// switch it (not on the model page itself, and not when `canSwitch` is false, e.g. during an evaluation session).
export async function loadStatus(target, { canSwitch = true } = {}) {
  try {
    const config = await api("/api/config");
    const docs = Object.values(config.documents).reduce((a, b) => a + b, 0);
    const switchable = canSwitch && location.pathname !== "/connect/llm";
    const model = config.llm_problem
      ? h("span", { class: "status-warn", title: config.llm_problem }, "AI 模型尚未設定")
      : `AI：${config.llm_label || config.llm_provider}`;
    target.replaceChildren(`${docs} 份資料｜`, model, !switchable ? ""
      : h("a", { class: "status-switch", href: "/connect/llm", title: "更換回答用的 AI 模型" }, config.llm_problem ? "設定" : "更換"));
    return config;
  } catch {
    target.textContent = "無法連線到伺服器";
    return null;
  }
}
