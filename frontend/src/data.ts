import type { Dashboard } from "./types";

/** The Python builder writes `dashboard/dist/data.json` next to the compiled
 *  app. Fetched at runtime rather than bundled so a fresh `make eval` is
 *  reflected by re-running the builder alone, with no rebuild of the app. */
export async function loadDashboard(): Promise<Dashboard> {
  const res = await fetch("./data.json");
  if (!res.ok) throw new Error(`could not load data.json (${res.status})`);
  return res.json();
}
