// Shared helpers for the step-by-step connect pages (/connect/github, /connect/notion, ...).
import { api, h } from "/static/common.js?v=0.2.0";

export const $ = (id) => document.getElementById(id);
export const post = (path, body) => api(path, { method: "POST", body: body || {} });
export const waiting = (text) => h("span", { class: "thinking" }, h("span", { class: "pulse", "aria-hidden": "true" }), text);

// Show `content` in the notice #id (hidden when empty); `kind` is "", "ok" or "error".
export function note(id, content, kind) {
  const el = $(id);
  if (kind !== undefined) el.className = "notice " + kind;
  el.hidden = !content;
  el.replaceChildren(...(content ? [content] : []));
}

// Disable the button while fn runs.
export async function busy(button, fn) {
  button.disabled = true;
  try { await fn(); } finally { button.disabled = false; }
}

// Steps shown as <section id="step-NAME"> plus the <ol id="steps"> indicator. Returns go(name).
export function stepper(order, onEnter = () => {}) {
  return function go(step) {
    const i = order.indexOf(step);
    order.forEach((s) => ($("step-" + s).hidden = s !== step));
    [...$("steps").children].forEach((li, j) => {
      li.className = j < i ? "done" : "";
      if (j === i) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
    onEnter(step);
    window.scrollTo({ top: 0 });
  };
}

// Mark every step as done (after the last one succeeds).
export function allStepsDone() {
  [...$("steps").children].forEach((li) => { li.className = "done"; li.removeAttribute("aria-current"); });
}

// ---- illustrations of the other service's pages (inline SVG, styled by the .ill-* classes) ----
export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// A browser-window frame around `inner` (SVG markup, 560x250 viewBox) with a caption.
export function frame(url, inner, label) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 250" role="img" aria-label="${label}">
    <rect class="ill-frame" x="1" y="1" width="558" height="248" rx="10"/>
    <rect class="ill-bar" x="1.5" y="1.5" width="557" height="30" rx="9"/>
    <circle class="ill-dot" cx="18" cy="16" r="5"/><circle class="ill-dot" cx="34" cy="16" r="5"/><circle class="ill-dot" cx="50" cy="16" r="5"/>
    ${url ? `<rect class="ill-box" x="70" y="9" width="300" height="15" rx="7"/><text class="ill-muted" x="80" y="20.5" font-size="10">${url}</text>` : ""}
    ${inner}</svg><figcaption>示意圖：${label}（實際畫面可能略有不同）</figcaption>`;
}
