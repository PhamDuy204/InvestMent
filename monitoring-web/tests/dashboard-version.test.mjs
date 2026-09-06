import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const dashboard = readFileSync(new URL("../components/dashboard.tsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");

test("V19 reuses the V18 dashboard instead of falling back to V13", () => {
  assert.match(dashboard, /displaySchemaVersion === "v19-monitoring-1"/);
  assert.match(dashboard, /V19 WebSocket Causal EV Paper Monitor/);
  assert.match(layout, /V21 Cohort-Calibrated Risk Paper Monitor/);
  assert.doesNotMatch(dashboard, /: "V13 Paper Monitor"}<\/span>/);
});

test("V20 dashboard labels paired win rate and account PnL per hour", () => {
  assert.match(dashboard, /displaySchemaVersion === "v20-monitoring-1"/);
  assert.match(dashboard, /V20 Execution-Aware Paper Monitor/);
  assert.match(dashboard, /Paired Win Rate/);
  assert.match(dashboard, /Account PnL\/hour/);
  assert.match(layout, /V21 Cohort-Calibrated Risk Paper Monitor/);
});

test("V21 dashboard identifies cohort-calibrated risk policy without losing account truth metrics", () => {
  const telemetry = readFileSync(new URL("../lib/telemetry.ts", import.meta.url), "utf8");
  assert.match(telemetry, /v21-monitoring-1/);
  assert.match(dashboard, /displaySchemaVersion === "v21-monitoring-1"/);
  assert.match(dashboard, /V21 Cohort-Calibrated Risk Paper Monitor/);
  assert.match(dashboard, /Account PnL\/hour/);
  assert.match(dashboard, /Public trade prints/);
});

test("V21 SSR fallback never renders legacy V20/V14 identity while telemetry loads", () => {
  assert.match(dashboard, /const displaySchemaVersion = telemetry\?\.schema_version \?\? "v21-monitoring-1"/);
  assert.match(dashboard, /telemetry \? money\(accountLast\?\.marked_equity \?\? telemetry\.equity, 4\) : money\(100, 4\)/);
  assert.doesNotMatch(dashboard, /: "V20 Execution-Aware Paper Monitor"}<\/span>/);
});

test("V21 radar uses cohort execution semantics instead of legacy maker hurdles", () => {
  assert.match(dashboard, /isV21 \? \(/);
  assert.match(dashboard, />Pair value</);
  assert.match(dashboard, />Abort value</);
  assert.match(dashboard, />P\(fill\)</);
  assert.match(dashboard, />P\(accept\)</);
  assert.match(dashboard, />Accept LB</);
  assert.match(dashboard, /WARMUP/);
  assert.match(dashboard, /NOT SIZED/);
  assert.match(dashboard, /NOT MODELED/);
});

test("V21 explains 90% as confidence bound, not a hard acceptance-rate gate", () => {
  assert.match(dashboard, /90% confidence lower bound/);
  assert.doesNotMatch(dashboard, /requires a ≥90% cohort acceptance point estimate/);
});
