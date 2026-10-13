import assert from "node:assert/strict";
import { SETTINGS_KEY, readSettings, validSettings, writeSettings } from "./demo-settings.ts";

const settings = { name: "Анна", account: "Магазин", email: "demo@example.com", timezone: "msk", cpa: "300", problems: true, digest: false, effect: true };
let stored = null;
const storage = {
  getItem(key) { assert.equal(key, SETTINGS_KEY); return stored; },
  setItem(key, value) { assert.equal(key, SETTINGS_KEY); stored = value; },
};
assert.equal(readSettings(storage), null);
writeSettings(storage, settings);
assert.deepEqual(readSettings(storage), settings);
assert.equal(validSettings({ ...settings, email: "", cpa: "" }), true);
assert.equal(validSettings({ ...settings, cpa: "10000000" }), true);
for (const patch of [{ name: " " }, { account: "" }, { email: "broken" }, { cpa: "0" }, { cpa: "10000001" }, { cpa: "NaN" }, { timezone: "unknown" }, { problems: "true" }]) {
  assert.equal(validSettings({ ...settings, ...patch }), false);
  assert.throws(() => writeSettings(storage, { ...settings, ...patch }));
}
stored = "{broken";
assert.throws(() => readSettings(storage));
stored = '{"name":"wrong schema"}';
assert.throws(() => readSettings(storage));
assert.throws(() => writeSettings({ setItem() { throw new Error("Storage unavailable"); } }, settings));
console.log("Demo settings validation and persistence checks passed");
