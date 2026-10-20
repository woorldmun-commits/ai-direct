export const SETTINGS_KEY = "adpilot.demo.settings.v1";

export type DemoSettings = {
  name: string;
  account: string;
  email: string;
  timezone: string;
  cpa: string;
  problems: boolean;
  digest: boolean;
  effect: boolean;
};

export function validSettings(value: unknown): value is DemoSettings {
  if (!value || typeof value !== "object") return false;
  const s = value as Record<string, unknown>;
  return (
    typeof s.name === "string" && s.name.trim().length > 0 && s.name.length <= 80 &&
    typeof s.account === "string" && s.account.trim().length > 0 && s.account.length <= 120 &&
    typeof s.email === "string" && s.email.length <= 254 &&
    (s.email === "" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.email)) &&
    typeof s.timezone === "string" && ["msk", "ekb", "nsk"].includes(s.timezone) &&
    typeof s.cpa === "string" &&
    (s.cpa === "" || (/^\d+$/.test(s.cpa) && Number(s.cpa) >= 1 && Number(s.cpa) <= 10_000_000)) &&
    typeof s.problems === "boolean" && typeof s.digest === "boolean" && typeof s.effect === "boolean"
  );
}

export function readSettings(storage: Pick<Storage, "getItem">): DemoSettings | null {
  const raw = storage.getItem(SETTINGS_KEY);
  if (raw === null) return null;
  const saved: unknown = JSON.parse(raw);
  if (!validSettings(saved)) throw new Error("Invalid demo settings");
  return saved;
}

export function writeSettings(storage: Pick<Storage, "setItem">, settings: DemoSettings) {
  if (!validSettings(settings)) throw new Error("Invalid demo settings");
  storage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
