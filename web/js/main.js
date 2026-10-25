import { api, ApiError, token } from "./api.js";
import { CameraError, capturePhoto, closeCamera, openCamera } from "./camera.js";
import { h, render } from "./dom.js";
import { inAppBrowser } from "./inapp.js";
import { locationJson, locationUnavailable, requestLocation } from "./location.js";
import { cameraScreen } from "./screens/camera.js";
import { cameraBlockedCard, openInChromeCard } from "./screens/help.js";
import { actionBar, photoPanel } from "./screens/result.js";
import { roomScreen } from "./screens/room.js";
import { roomsScreen } from "./screens/rooms.js";
import { agentSteps, savedCard } from "./screens/saved.js";

const app = /** @type {HTMLElement} */ (document.getElementById("app"));

/** @type {{roomId: string, room: any, sessionId: string} | null} */
let visit = null;
/** @type {MediaStream | null} */
let stream = null;

const goRooms = () => { location.hash = "#/rooms"; };

function notice(title, message, action) {
  render(app, h("section", { class: "notice" },
    h("h1", {}, title),
    h("p", {}, message),
    action ? h("button", { class: "button", onClick: action.run }, action.label) : null));
}

function failed(error) {
  if (error instanceof ApiError && error.code === "invalid_link") {
    notice("Link kaam nahi kar raha", error.message);
  } else if (error instanceof ApiError && error.code === "session_expired") {
    visit = null;
    notice("Session purana ho gaya", error.message, { label: "Rooms pe wapas", run: goRooms });
  } else {
    notice("Kuch gadbad hui", error.message ?? String(error),
      { label: "Dobara try karo", run: () => route() });
  }
}

async function showRooms() {
  visit = null;
  const round = await api("/round");
  render(app, roomsScreen(round, (roomId) => { location.hash = `#/room/${roomId}`; }));
}

async function showRoom(roomId) {
  const room = await api(`/rooms/${encodeURIComponent(roomId)}`);
  if (room.status === "done") {
    const latest = await api(`/rooms/${encodeURIComponent(roomId)}/latest`);
    render(app,
      h("section", { class: "result" },
        h("button", { class: "back", onClick: goRooms }, "‹ Rooms"),
        h("h2", {}, `Room ${roomId}`),
        savedCard(latest.saved),
        agentSteps(latest.summary)),
      actionBar("Rooms pe wapas", goRooms));
    return;
  }
  render(app, ...roomScreen(room, {
    back: goRooms,
    takePhoto: () => { location.hash = `#/camera/${roomId}`; },
  }));
}

async function startVisit(roomId) {
  if (visit?.roomId === roomId) return visit;
  const room = await api(`/rooms/${encodeURIComponent(roomId)}`);
  const session = await api(`/rooms/${encodeURIComponent(roomId)}/sessions`, { method: "POST" });
  visit = { roomId, room, sessionId: session.session_id };
  return visit;
}

async function showCamera(roomId, hint) {
  const current = await startVisit(roomId);
  const screen = cameraScreen({
    roomId,
    hint: hint ?? current.room.hint,
    onCancel: () => { location.hash = `#/room/${roomId}`; },
    onShoot: async () => {
      if (!stream) return;
      screen.setBusy(true);
      try {
        const blob = await capturePhoto(stream, screen.video);
        closeCamera(stream);
        stream = null;
        await submit(blob, crypto.randomUUID());
      } catch (error) {
        screen.setBusy(false);
        failed(error);
      }
    },
  });
  render(app, screen.element);
  screen.setBusy(true);
  try {
    stream = await openCamera(screen.video);
    screen.setBusy(false);
  } catch (error) {
    if (error instanceof CameraError && error.kind === "blocked") {
      render(app, ...cameraBlockedCard(() => showCamera(roomId, hint).catch(failed)));
      return;
    }
    if (error instanceof CameraError) {
      notice("Camera nahi khula", error.message,
        { label: "Dobara try karo", run: () => showCamera(roomId, hint).catch(failed) });
      return;
    }
    throw error;
  }
  requestLocation().then(() => {
    if (locationUnavailable()) screen.note("Location band hai, photo phir bhi save hogi.");
  });
}

async function submit(blob, photoId) {
  const url = URL.createObjectURL(blob);
  const panel = photoPanel(url, null, "Photo check ho rahi hai…", "info");
  render(app, h("section", { class: "result" }, panel.panel));
  const form = new FormData();
  form.append("photo", blob, "photo.jpg");
  form.append("client_photo_id", photoId);
  form.append("location", locationJson());
  let result;
  try {
    result = await api(`/sessions/${visit?.sessionId}/photos`, { body: form, timeoutMs: 60000 });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 0 || error.status >= 500)) {
      panel.say("Photo nahi gayi. Network check karke dobara bhejo.", "problem");
      app.append(actionBar("Dobara bhejo", () => submit(blob, photoId)));
      return;
    }
    throw error;
  }
  showResult(url, result);
}

function showResult(url, result) {
  const roomId = visit?.roomId ?? "";
  const problem = result.action === "retake" || result.action === "new_photo";
  const tone = problem ? "problem" : result.action === "review" ? "review" : "ok";
  const line = result.action === "review" ? "Review ke liye bhej diya" : result.hint;
  const panel = photoPanel(url, result, line, tone);
  const body = [panel.panel];

  if (result.saved) {
    body.push(savedCard(result.saved), agentSteps(result.summary));
    navigator.vibrate?.(60);
  } else if (result.action === "confirm" && result.confirm) {
    const { serial, serial_last4: tail, reading } = result.confirm;
    body.push(h("section", { class: "confirm-card" },
      h("p", { class: "serial-line mono" }, `SN-${serial.slice(0, -4)}`, h("span", { class: "tail" }, tail)),
      h("p", {}, "Pehli reading: ", h("strong", { class: "mono" }, reading)),
      h("h1", {}, `Ye meter Room ${roomId} ka hai?`)));
    render(app, h("section", { class: "result" }, ...body),
      h("div", { class: "action-bar two" },
        h("button", { class: "button secondary", onClick: () => answer("no") }, "Nahi, dobara photo lo"),
        h("button", { class: "button", onClick: () => answer("yes") }, "Haan, jodo")));
    panel.redraw();
    return;
  }
  if (result.action === "review") {
    body.push(h("div", { class: "review-card" },
      h("h1", {}, `Room ${roomId} review ke liye bhej diya`),
      h("p", {}, result.hint),
      h("p", {}, "Reading save nahi hui. Aap agle room pe ja sakte ho.")),
    agentSteps(result.summary));
  }

  const bar = problem
    ? actionBar("Dobara photo lo", () => showCamera(roomId, result.hint).catch(failed))
    : result.action === "review"
      ? actionBar("Agle room pe jao", goRooms)
      : actionBar("Rooms pe wapas", goRooms);
  render(app, h("section", { class: "result" }, ...body), bar);
  playSteps(panel, result, tone, line);
}

async function answer(choice) {
  const roomId = visit?.roomId ?? "";
  const buttons = app.querySelectorAll(".action-bar .button");
  buttons.forEach((b) => { b.disabled = true; });
  try {
    const result = await api(`/sessions/${visit?.sessionId}/confirm`, { json: { answer: choice } });
    if (choice === "no") {
      await showCamera(roomId, result.hint);
      return;
    }
    navigator.vibrate?.(60);
    visit = null;
    render(app,
      h("section", { class: "result" }, h("h2", {}, `Room ${roomId}`), savedCard(result.saved), agentSteps(result.summary)),
      actionBar("Agle room pe jao", goRooms));
  } catch (error) {
    if (error instanceof ApiError && error.code === "meter_taken") {
      visit = null;
      notice("Meter pehle se juda hai", error.message, { label: "Rooms pe wapas", run: goRooms });
      return;
    }
    failed(error);
  }
}

function playSteps(panel, result, tone, finalLine) {
  const reread = result.steps?.find((s) => s.step === "reread");
  const first = result.steps?.find((s) => s.step === "perceive");
  if (!reread || !first || !result.display) {
    panel.redraw();
    return;
  }
  const threshold = result.display.threshold;
  const unclear = first.confidences.map((c, i) => (c < threshold ? i : -1)).filter((i) => i >= 0);
  panel.say("Ek digit saaf nahi, dobara padh raha hoon.", "info");
  panel.redraw({ confidences: first.confidences, unclear });
  setTimeout(() => {
    panel.redraw();
    panel.say(finalLine, tone);
  }, 1400);
}

const routes = [
  [/^#\/camera\/([^/]+)$/, (roomId) => showCamera(roomId)],
  [/^#\/room\/([^/]+)$/, showRoom],
  [/^(?:#\/rooms)?$/, showRooms],
];

async function route() {
  closeCamera(stream);
  stream = null;
  if (!token) {
    notice("Link kaam nahi kar raha", "Ye link sahi nahi hai, admin se naya link maango.");
    return;
  }
  if (inAppBrowser()) {
    render(app, ...openInChromeCard());
    return;
  }
  const hash = location.hash;
  const match = routes.find(([pattern]) => pattern.test(hash));
  if (!match) {
    goRooms();
    return;
  }
  render(app, h("p", { class: "loading" }, "Load ho raha hai…"));
  try {
    await match[1](...hash.match(match[0]).slice(1).map(decodeURIComponent));
  } catch (error) {
    failed(error);
  }
}

window.addEventListener("hashchange", route);
route();
