import { h } from "../dom.js";

/**
 * @param {{roomId: string, hint: string, onShoot: () => void, onCancel: () => void}} props
 */
export function cameraScreen(props) {
  const video = /** @type {HTMLVideoElement} */ (h("video", { class: "camera-video", autoplay: true, muted: true, playsinline: true }));
  const shutter = /** @type {HTMLButtonElement} */ (
    h("button", { class: "shutter", "aria-label": "Photo khincho", onClick: props.onShoot }));
  const note = h("p", { class: "camera-note", hidden: true });
  const element = h("div", { class: "camera" },
    video,
    h("div", { class: "frame-guide", "aria-hidden": "true" }),
    h("p", { class: "camera-hint" }, `Room ${props.roomId} · ${props.hint}`),
    note,
    h("div", { class: "camera-bar" },
      h("button", { class: "camera-cancel", onClick: props.onCancel }, "Wapas"),
      shutter,
      h("span", { class: "camera-spacer" })),
  );
  return {
    element,
    video,
    /** @param {string} text */
    note(text) {
      note.textContent = text;
      note.hidden = false;
    },
    /** @param {boolean} busy */
    setBusy(busy) {
      shutter.disabled = busy;
      element.classList.toggle("busy", busy);
    },
  };
}
