// Rates come from the Python backend (see backend/app/rates.py).
export async function loadRates(force = false) {
  const res = await fetch(`/api/rates${force ? "?refresh=true" : ""}`);
  if (!res.ok) throw new Error(`сервер ответил ${res.status}`);
  return { ...(await res.json()), mode: "live" };
}
