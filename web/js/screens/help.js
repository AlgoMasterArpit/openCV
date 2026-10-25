import { h } from "../dom.js";
import { chromeIntentUrl } from "../inapp.js";

const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs, text) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text) node.textContent = text;
  return node;
}

/** A drawing of Chrome's address bar: lock icon → Permissions → Camera → Allow. */
function permissionSketch() {
  const svg = el("svg", { viewBox: "0 0 320 150", class: "sketch", role: "img",
    "aria-label": "Address bar mein lock icon, phir Permissions, phir Camera Allow" });
  svg.append(
    el("rect", { x: 8, y: 8, width: 304, height: 36, rx: 18, class: "sk-bar" }),
    el("circle", { cx: 32, cy: 26, r: 13, class: "sk-hot" }),
    el("rect", { x: 26, y: 24, width: 12, height: 9, rx: 2, class: "sk-icon" }),
    el("path", { d: "M28 24v-3a4 4 0 0 1 8 0v3", class: "sk-line" }),
    el("text", { x: 54, y: 31, class: "sk-text" }, "meter-round…/r/…"),
    el("rect", { x: 20, y: 56, width: 210, height: 82, rx: 10, class: "sk-menu" }),
    el("text", { x: 34, y: 82, class: "sk-text" }, "Permissions"),
    el("text", { x: 34, y: 108, class: "sk-text" }, "Camera"),
    el("rect", { x: 150, y: 94, width: 66, height: 22, rx: 11, class: "sk-hot" }),
    el("text", { x: 164, y: 110, class: "sk-text sk-on" }, "Allow"),
  );
  return svg;
}

/** @param {() => void} retry */
export function cameraBlockedCard(retry) {
  return [
    h("section", { class: "notice" },
      h("h1", {}, "Camera band hai"),
      h("p", {}, "Meter ki photo ke liye camera chahiye."),
      permissionSketch(),
      h("ol", { class: "steps" },
        h("li", {}, "Upar address bar mein lock icon pe tap karo"),
        h("li", {}, "Permissions → Camera → Allow"),
        h("li", {}, "Neeche button dabao"))),
    h("div", { class: "action-bar" }, h("button", { class: "button", onClick: retry }, "Dobara try karo")),
  ];
}

export function openInChromeCard() {
  return [
    h("section", { class: "notice" },
      h("h1", {}, "Ye link Chrome mein kholo"),
      h("p", {}, "WhatsApp ke andar camera theek se nahi chalta. Chrome mein link kholo, phir meter round shuru karo.")),
    h("div", { class: "action-bar" },
      h("a", { class: "button link-button", href: chromeIntentUrl() }, "Chrome mein kholo")),
  ];
}
