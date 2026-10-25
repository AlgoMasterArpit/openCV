/**
 * @param {string} tag
 * @param {Record<string, any>} [attrs]
 * @param {...(Node|string|null|undefined|false)} children
 * @returns {HTMLElement}
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "class") el.className = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child);
  }
  return el;
}

/** @param {HTMLElement} root @param {...Node} nodes */
export function render(root, ...nodes) {
  root.replaceChildren(...nodes);
  window.scrollTo(0, 0);
}

const DAY_MONTH = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });

/** @param {string} iso a date ("2026-10-21") or a timestamp with offset */
export function shortDate(iso) {
  const value = iso.length === 10 ? `${iso}T12:00:00+05:30` : iso;
  return DAY_MONTH.format(new Date(value));
}

export const STATUS_LABEL = {
  pending: "Baaki",
  done: "Ho gaya",
  review: "Review mein",
  needs_meter: "Meter jodna hai",
};
