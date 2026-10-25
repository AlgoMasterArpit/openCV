const TIMEOUT_MS = 5000;

/** @type {{lat: number, lon: number, accuracy: number} | null} */
let last = null;
/** @type {"unknown"|"ok"|"unavailable"} */
let state = "unknown";

/**
 * Asked only after the camera is allowed, so two permission popups never stack.
 * Never blocks a photo: a denial or a 5-second silence just marks location unavailable.
 * @returns {Promise<"ok"|"unavailable">}
 */
export function requestLocation() {
  if (!("geolocation" in navigator)) {
    state = "unavailable";
    return Promise.resolve(state);
  }
  return new Promise((resolve) => {
    const done = (/** @type {"ok"|"unavailable"} */ next) => {
      state = next;
      resolve(next);
    };
    const timer = setTimeout(() => done(last ? "ok" : "unavailable"), TIMEOUT_MS);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        clearTimeout(timer);
        last = {
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          accuracy: position.coords.accuracy,
        };
        done("ok");
      },
      () => {
        clearTimeout(timer);
        done("unavailable");
      },
      { enableHighAccuracy: true, timeout: TIMEOUT_MS, maximumAge: 60000 },
    );
  });
}

export function locationJson() {
  return JSON.stringify(last ?? {});
}

export function locationUnavailable() {
  return state === "unavailable";
}
