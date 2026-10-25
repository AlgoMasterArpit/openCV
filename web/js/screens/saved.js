import { h, shortDate } from "../dom.js";

const SVG = "http://www.w3.org/2000/svg";

function tick() {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "tick");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", "M5 12.5l4.5 4.5L19 7.5");
  svg.append(path);
  return svg;
}

/**
 * @param {{label: string, decided_by: string}[]} summary
 */
export function agentSteps(summary) {
  if (!summary?.length) return null;
  return h("section", { class: "agent-steps" },
    h("h2", {}, "Agent ne kya kiya"),
    h("ol", {}, ...summary.map((line) => h("li", {},
      h("span", {}, line.label),
      line.decided_by === "llm" || line.decided_by === "rule"
        ? h("span", { class: `by ${line.decided_by}` }, line.decided_by === "llm" ? "LLM" : "rule")
        : null))));
}

/**
 * @param {{status: string, reading: string, units: number|null, unit_label: string|null,
 *          co2_kg: number|null, recorded_at: string}} saved
 */
export function savedCard(saved) {
  const baseline = saved.status === "baseline";
  const units = saved.units === null || saved.units === undefined
    ? null
    : `${saved.units} ${saved.unit_label ?? "units"} · pichhli reading se ab tak`;
  return h("section", { class: "saved-card" },
    h("div", { class: "saved-head" }, tick(), h("span", {}, baseline ? "Meter juda · Baseline save" : "Reading save")),
    h("p", { class: "reading mono" }, saved.reading),
    units ? h("p", {}, units) : null,
    saved.co2_kg !== null && saved.co2_kg !== undefined ? h("p", {}, `${saved.co2_kg} kg CO₂`) : null,
    h("p", { class: "saved-when" }, `${shortDate(saved.recorded_at)} ko save hui`));
}
