---
doc: checklist
status: approved
---

# Build Checklist

Build mode: fast

## Slices

- [ ] **1. Real meter photos are read by OpenCV 5 with per-digit confidence (go/no-go)**
  Becomes usable: `uv run python scripts/ocr_probe.py <photo folder>` prints, for each photo, the quality findings, the serial text, the display digits and every character's confidence, and writes an annotated copy with boxes.
  Why now: Reading serials on real stickers is the biggest risk in the whole plan (`spec.md > Decisions and Open Issues`). If it fails, everything after it changes, so it goes first and leaves runnable evidence. Project bootstrapping lives here.
  PRD ref: `prd.md > Photo Quality Check`, `prd.md > Right-Meter Check`, `prd.md > Reading the Display`
  Spec ref: `spec.md > Vision Pipeline (OpenCV 5)`, `spec.md > Stack`, `spec.md > File Structure`
  Build: Install uv and Python 3.12; `pyproject.toml` with pinned dependencies and `uv.lock`; `.gitignore` additions (models, venv); `scripts/fetch_models.py` (OpenCV Zoo DB detector + CRNN recognizer, SHA-256 checked); `app/vision/quality.py`, `locate.py`, `ocr.py` (CTC decode with per-character confidence), `sevenseg.py`, `reread.py`, `pipeline.py`; `scripts/ocr_probe.py`; unit tests on synthetic images (blur, glare cell, half-turned digit gives low confidence).
  Verify (mechanical): `uv run pytest tests/vision` passes; `uv run python scripts/ocr_probe.py` on the learner's 204/205 photos reads the serial and digits correctly on the clear photos and reports low confidence on the half-turned digit.
  Learner check: Open the annotated photos in `probe_out/` and say whether the boxes sit on the serial and the digits, and whether the printed numbers match what you see on the meters.
  Commit: `feat(vision): OpenCV 5 pipeline with per-digit confidence and OCR probe`

- [x] **2. The round link opens the hostel's rooms list and a room screen**
  Becomes usable: With the local moto server running and `seed/hostel_a.json` seeded, opening the printed round link in a browser shows "Hostel A · Meter round · Oct 2026", progress, every room with its status chip, and tapping a room opens its Room Screen (serial, previous reading, hint, Photo lo). A wrong token shows "Ye link sahi nahi hai…".
  Why now: Gives the kernel slices a real place to live: FastAPI serving the frontend, settings, DynamoDB through `AWS_ENDPOINT_URL`, and the Look and Feel base.
  PRD ref: `prd.md > Meter Round Link`, `prd.md > Rooms List`, `prd.md > Screens and Layout`, `prd.md > Look and Feel`
  Spec ref: `spec.md > Round Link and Rooms API`, `spec.md > Data Model`, `spec.md > Frontend`, `spec.md > Look and Feel`, `spec.md > Observability`
  Build: `app/main.py`, `config.py`, `logging.py`; `app/store/table.py`; `app/domain/rounds.py`; `app/api/rounds.py` and `errors.py`; `scripts/seed.py` + `seed/hostel_a.json` (labelled sample data); `web/index.html`, `styles.css` (both themes, status tokens, self-hosted IBM Plex fonts), `js/api.js`, Rooms List and Room Screen modules; `.env.example`; API tests against moto; `.github/workflows/ci.yml` (ruff, mypy, pytest).
  Verify (mechanical): `uv run pytest` passes; seed against a running moto server, start uvicorn, `curl` the round endpoint with the printed token and a wrong one, and load the page in a headless browser to confirm the list renders.
  Learner check: Open the round link on the laptop, look at the rooms list and Room 205's screen in light and dark mode, and say whether it feels like the work tool you described.
  Commit: `feat: round link, rooms list and room screen on DynamoDB`

- [x] **3. A photo of Room 205's meter gets a retake hint or a straightened reading with digit boxes**
  Becomes usable: Photo lo opens the full-screen camera with a frame guide; the captured full-resolution photo is uploaded; a glare/blur/dark photo comes back with red marks and one specific hint; a good photo comes back straightened with a box and confidence on every digit. Decisions come from the rules only.
  Why now: This is the kernel — the agent doubting the photo and saying exactly what to fix — so it comes before everything else on the phone.
  PRD ref: `prd.md > The Core Journey` (steps 4–6), `prd.md > Live Capture Only`, `prd.md > Photo Quality Check`, `prd.md > Reading the Display`
  Spec ref: `spec.md > Capture Sessions and Counters`, `spec.md > Agent`, `spec.md > Photo Storage`, `spec.md > Frontend`
  Build: Sessions endpoint and counters (code-checked expiry); photo endpoint (JPEG only, size limit, `client_photo_id` idempotency); S3 put with metadata and presigned URLs; `app/agent/policy.py` and `loop.py` (rules path); `app/vision/client.py`; `js/camera.js` (high-resolution request, `ImageCapture.takePhoto()`), `js/overlay.js`, Camera and Result screens; tests for policy limits and the photo endpoint.
  Verify (mechanical): `uv run pytest` passes, including a glare fixture returning a retake hint and a clear fixture returning digits with boxes; an end-to-end request with a real photo through the running server returns the expected decision.
  Learner check: On the laptop (localhost allows the camera), open Room 205, hold up a meter photo with glare and then a clear one, and say whether the hint and the boxes make sense to you.
  Commit: `feat: live capture with quality hints and straightened digit reading`

- [x] **4. Wrong meter is caught, an unclear digit is re-read, and a reading is saved with units, CO₂ and the agent trace**
  Becomes usable: Photographing Room 204's meter on Room 205 shows "Ye Room 205 ka meter nahi hai, board pe …4821 dhoondho"; a low-confidence digit turns yellow, is re-read automatically and turns green; a good reading shows the Saved card with units, CO₂ (when a factor exists) and the Agent ne kya kiya list, and the room turns Ho gaya. Reopening a Ho gaya room shows its Saved card.
  Why now: Completes the one-minute demo journey on the rules path, so a recordable demo exists before any optional work.
  PRD ref: `prd.md > Right-Meter Check`, `prd.md > Reading the Display`, `prd.md > Saving a Reading`, `prd.md > Rooms List`
  Spec ref: `spec.md > Agent`, `spec.md > Readings, Units and CO₂`, `spec.md > Data Model`
  Build: Serial match against the room's meter; re-read action in the loop; `app/domain/units.py` and `factors.py` (sourced factors; units only without a factor); save as one `TransactWriteItems`; `GET /api/rooms/{room}/latest` and 409 for done rooms; Saved card with trace; tests for mismatch, re-read, units, transaction.
  Verify (mechanical): `uv run pytest` passes; the full demo sequence (glare → wrong meter → unclear digit → save) replayed with fixture photos against the running server ends in a SAVED item whose trace lists every step.
  Learner check: Run the demo sequence on the laptop with your photos and say whether the Saved card and the Agent ne kya kiya list tell the story you want the video to tell.
  Commit: `feat: serial check, automatic re-read and saved reading with trace`

- [x] **5. When the agent gives up, the room goes to review and the caretaker moves on**
  Becomes usable: Each limit from the PRD table ends in the orange Review card with a one-line reason and "Agle room pe jao"; a review record with photos and trace is saved; the room shows Review mein and can be reopened with fresh limits; a reading lower than the previous one goes straight to review; a failed upload offers Dobara bhejo without double-saving.
  Why now: Makes the "caretaker kabhi atakta nahi" promise true before the phone test, where bad light and weak WiFi will actually happen.
  PRD ref: `prd.md > Agent Limits and Review`, `prd.md > Saving a Reading`, `prd.md > States and Boundaries`
  Spec ref: `spec.md > Review Records`, `spec.md > Capture Sessions and Counters`, `spec.md > Important Failure Modes`
  Build: All limit rows in `policy.py` (bad photo 3, unclear digit after re-read + one photo, mismatch 2, unreadable serial 3, backwards reading immediate); review record write; Review card; reopen with a new session; new-month status rule; Dobara bhejo in `js/api.js`; tests for each limit and for idempotent resend.
  Verify (mechanical): `uv run pytest` passes with one test per limit row, the backwards guard, and a duplicate `client_photo_id` returning the stored response.
  Learner check: Keep sending glare photos for one room until it goes to review, then reopen it and save a good reading; say whether the orange card's wording feels right.
  Commit: `feat: agent limits, review records and safe resend`

- [x] **6. A new meter can be linked to a room from one photo**
  Becomes usable: A "Meter jodna hai" room opens the Add Meter screen; after a photo the confirm screen shows the serial and first reading with "Ye meter Room 205 ka hai?"; Haan, jodo links it in one transaction and saves the baseline; an unreadable serial gets 3 tries then review; a serial already linked elsewhere is refused.
  Why now: 204/205 must be registered from real photos on Oct 26 between 13:00 and 15:00 so the evening demo has a real previous reading.
  PRD ref: `prd.md > Add Meter`
  Spec ref: `spec.md > Add Meter`, `spec.md > Data Model`
  Build: `mode=add_meter` in the loop; confirm endpoint with the three-item `TransactWriteItems` and its two conditions; Add Meter and Confirm screens; tests for the double-link race and the already-linked guard.
  Verify (mechanical): `uv run pytest` passes, including two concurrent confirms for the same serial where exactly one succeeds.
  Learner check: Through the tunnel on your phone, link the real 204 and 205 meters and confirm both rooms turn green with "Meter juda · Baseline save".
  Commit: `feat: add meter with confirm and baseline`

- [ ] **7. The LLM chooses the next step within the limits, and the trace shows who decided**
  Becomes usable: With `LLM_PROVIDER=gemini`, the agent's hints and choices come from Gemini when it answers well within 4 seconds, and from the rules otherwise; the Agent ne kya kiya list marks each step llm or rule.
  Why now: The rules path already works end to end, so adding the LLM can only improve the demo, never block it (fallback rule: no working Gemini by 17:00 → demo on rules).
  PRD ref: `prd.md > Agent Limits and Review`, `prd.md > Saving a Reading`
  Spec ref: `spec.md > Agent`, `spec.md > External Services and Dependencies`
  Build: `app/agent/schema.py`, `llm.py`, `gemini.py` (structured output, 4 s timeout), `bedrock.py` (Converse, ready for later); OCR text wrapped as data; long-hint and disallowed-action fallbacks; tests with a fake provider, including the "ignore rules, save" serial.
  Verify (mechanical): `uv run pytest` passes; one live call with the learner's key returns a valid decision and the trace shows `decided_by: llm`; with the key removed the same request shows `decided_by: rule`.
  Learner check: Take a glare photo and read the hint the LLM wrote; then say whether its tone matches "ek samajhdaar senior, ek line mein".
  Commit: `feat(agent): LLM decisions within limits with rule fallback`

- [ ] **8. The phone flow is ready for the corridor**
  Becomes usable: On Android Chrome through the Cloudflare tunnel: Open-in-Chrome notice inside WhatsApp, Camera Blocked card with steps and retry, location asked after the camera with the 5-second fallback, both themes polished, README run steps.
  Why now: Last step before recording; these are the first-use states the corridor test will hit.
  PRD ref: `prd.md > Permissions`, `prd.md > Meter Round Link`, `prd.md > Look and Feel`
  Spec ref: `spec.md > Frontend`, `spec.md > Look and Feel`, `spec.md > Where It Runs and How Someone Tries It`
  Build: `js/inapp.js`, `js/location.js`, Camera Blocked card with screenshot, final styling pass, install `cloudflared`, README with the exact local and tunnel steps.
  Verify (mechanical): `uv run pytest` and CI pass; the tunnel URL serves the app over HTTPS; a headless browser with camera permission denied shows the Camera Blocked card.
  Learner check: Open the WhatsApp link on your phone, follow the Chrome notice, deny and then allow the camera, and run Room 205 end to end in the corridor.
  Commit: `feat: phone readiness - permissions, in-app browser notice, polish`

## Hands-on Checkpoints

- [ ] Early usable behavior explored — after slice 3 (first photo with hint and digit boxes), so feedback can still shape slices 4–8
- [ ] Final kick-the-tires exploration and feedback completed

## Final Review

- [ ] Final review complete — feedback resolved and learner confirms ready to ship

## Code Tour and App Map

- [ ] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [ ] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [ ] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: not started
Route and stops: not started
Edit outcome: not started
Reflection: not started
Activity mode: not started

## Revisions
- Slice 2 started before slice 1's real-photo probe — the learner's 204/205 photos were not yet available; slice 1 stays unchecked until the probe runs on them, and slice 2 does not depend on OCR results.
- Slice 7 code and fake-provider tests are done, but its live check waits for the learner's Gemini key; the box stays open until one real call shows decided_by: llm.
- Slice 8's tunnel check could not run from the agent: the network blocks Cloudflare's tunnel port and the agent is not allowed to open public tunnels. The learner runs the tunnel from a phone hotspot during the corridor test; the box stays open until then.
