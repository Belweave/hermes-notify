// SPDX-License-Identifier: Apache-2.0
export type ActivityDesignTemplate = "standard" | "ring" | "hero" | "terminal" | "steps" | "approval" | "shell" | "verdict" | "signal";
export interface ActivityDesign {
  version: 1;
  template?: ActivityDesignTemplate;
  appearance?: "system" | "light" | "dark";
  density?: "comfortable" | "compact";
  emphasis?: "balanced" | "title" | "status" | "progress";
  showDetail?: boolean;
  showSymbol?: boolean;
}
export interface ActivityDesignOptions { kind?: "progress" | "ask" }
export interface ActivityDesignCatalogEntry {
  template: ActivityDesignTemplate;
  kind: "progress" | "ask";
  intent: string;
  constraints: string[];
  design: ActivityDesign;
  example: string;
}
export const ACTIVITY_DESIGN_MAX_BYTES: 16384;
export const activityDesignSchema: Readonly<Record<string, unknown>>;
/** Throws TypeError for invalid configuration, returning a copy without filling omitted fields. */
export function validateActivityDesign(value: unknown, options?: ActivityDesignOptions): ActivityDesign;
export function parseActivityDesign(json: string, options?: ActivityDesignOptions): ActivityDesign;
export function activityDesign(template: ActivityDesignTemplate): ActivityDesign;
export function activityDesignCatalog(): ActivityDesignCatalogEntry[];
