// Rates come from the Python backend (see backend/app/rates.py), which reports
// each rate's own provider timestamp. Map its snake_case payload to the shape
// the UI uses, so the browser-only build and this one stay interchangeable.
export async function loadRates(force = false) {
  const res = await fetch(`/api/rates${force ? "?refresh=true" : ""}`);
  if (!res.ok) throw new Error(`сервер ответил ${res.status}`);
  const d = await res.json();
  return {
    mode: "live",
    rates: d.rates,
    meta: Object.fromEntries(
      Object.entries(d.meta ?? {}).map(([code, m]) => [code, { src: m.source, asOf: m.as_of }])
    ),
    official: Object.fromEntries(
      Object.entries(d.official ?? {}).map(([code, o]) => [code, { ...o, asOf: o.as_of }])
    ),
    change_24h: d.change_24h ?? {},
    fetched_at: d.fetched_at,
  };
}
