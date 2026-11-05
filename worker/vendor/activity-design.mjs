// src/live-activities/design.mjs
var ACTIVITY_DESIGN_MAX_BYTES = 16384;
var progressTemplates = ["standard", "ring", "hero", "terminal", "steps"];
var askTemplates = ["approval", "shell", "verdict", "signal"];
var enums = {
  template: [...progressTemplates, ...askTemplates],
  appearance: ["system", "light", "dark"],
  density: ["comfortable", "compact"],
  emphasis: ["balanced", "title", "status", "progress"]
};
var activityDesignSchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  title: "Notify Live Activity design",
  type: "object",
  additionalProperties: false,
  required: ["version"],
  properties: {
    version: { const: 1 },
    ...Object.fromEntries(Object.entries(enums).map(([key, values]) => [key, { type: "string", enum: values }])),
    showDetail: { type: "boolean" },
    showSymbol: { type: "boolean" }
  }
};
function freezeTree(value) {
  for (const item of Object.values(value)) if (item && typeof item === "object") freezeTree(item);
  return Object.freeze(value);
}
freezeTree(activityDesignSchema);
function validateActivityDesign(value, { kind } = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError("design must be a JSON object with version: 1");
  for (const key of Object.keys(value)) {
    if (!Object.hasOwn(activityDesignSchema.properties, key)) throw new TypeError(`Unknown design key ${JSON.stringify(key)}; allowed: ${Object.keys(activityDesignSchema.properties).join(", ")}`);
  }
  if (value.version !== 1) throw new TypeError("design.version is required and must be 1");
  for (const [key, values] of Object.entries(enums)) {
    if (Object.hasOwn(value, key) && !values.includes(value[key])) throw new TypeError(`design.${key} must be one of: ${values.join(", ")}`);
  }
  for (const key of ["showDetail", "showSymbol"]) {
    if (Object.hasOwn(value, key) && typeof value[key] !== "boolean") throw new TypeError(`design.${key} must be a boolean`);
  }
  if (kind !== void 0 && !["progress", "ask"].includes(kind)) throw new TypeError("design kind must be progress or ask");
  if (value.template && kind && !(kind === "progress" ? progressTemplates : askTemplates).includes(value.template)) throw new TypeError(`design.template ${JSON.stringify(value.template)} is not valid for ${kind}; use ${(kind === "progress" ? progressTemplates : askTemplates).join(", ")}`);
  return { ...value };
}
function parseActivityDesign(json, options) {
  if (typeof json !== "string") throw new TypeError("design input must be a JSON string");
  if (new TextEncoder().encode(json).byteLength > ACTIVITY_DESIGN_MAX_BYTES) throw new TypeError(`design JSON must be at most ${ACTIVITY_DESIGN_MAX_BYTES} bytes`);
  let value;
  try {
    value = JSON.parse(json);
  } catch {
    throw new TypeError("design must contain valid JSON (a standalone object, not an activity payload)");
  }
  return validateActivityDesign(value, options);
}
function activityDesign(template) {
  return validateActivityDesign({ version: 1, template, appearance: "system", density: "comfortable", emphasis: "balanced", showDetail: true, showSymbol: true });
}
function activityDesignCatalog() {
  const intents = {
    standard: "Clear status and a linear progress indicator",
    ring: "Progress-led circular presentation",
    hero: "Title-led status presentation",
    terminal: "Compact operational status",
    steps: "Step-oriented progress",
    approval: "Clear human decision",
    shell: "Operational human decision",
    verdict: "Prominent decision title",
    signal: "Concise human decision"
  };
  return Object.entries(intents).map(([template, intent]) => ({
    template,
    kind: progressTemplates.includes(template) ? "progress" : "ask",
    intent,
    constraints: ["System-controlled geometry and Dynamic Island layout", "Native actions and privacy protections remain enforced", ...askTemplates.includes(template) ? ["Live Activity approval or yes/no only; no text reply"] : ["Ongoing progress activities only"]],
    design: activityDesign(template),
    example: askTemplates.includes(template) ? `notify send ask "Continue release?" --approval --live-activity --design-file ${template}.json` : `notify activity start --title "Release" --status "Running checks" --design-file ${template}.json`
  }));
}
export {
  ACTIVITY_DESIGN_MAX_BYTES,
  activityDesign,
  activityDesignCatalog,
  activityDesignSchema,
  parseActivityDesign,
  validateActivityDesign
};
