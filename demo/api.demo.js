// Data source for the single-file build (GitHub Pages and the artifact demo):
// no backend, so the browser asks the public APIs directly, in the same order
// as backend/app/rates.py. Sample rates are the last resort.
const DEMO_RATES = { USD: 1, RUB: 82.4, IDR: 16480, BTC: 1 / 112500, ETH: 1 / 4150 };
const CODES = ["RUB", "IDR", "BTC", "ETH"];

const getJSON = (url) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${new URL(url).host} ${r.status}`);
    return r.json();
  });

async function coinbaseChange() {
  const one = async (code) => {
    const s = await getJSON(`https://api.exchange.coinbase.com/products/${code}-USD/stats`);
    return [code, ((s.last - s.open) / s.open) * 100];
  };
  return Object.fromEntries(await Promise.all(["BTC", "ETH"].map(one)));
}

async function loadRates() {
  const rates = { USD: 1 };
  let change = {};
  const sources = [];

  const [cb, cbChange] = await Promise.allSettled([
    getJSON("https://api.coinbase.com/v2/exchange-rates?currency=USD"),
    coinbaseChange(),
  ]);
  if (cb.status === "fulfilled") {
    for (const c of CODES) if (cb.value.data.rates[c]) rates[c] = Number(cb.value.data.rates[c]);
    sources.push("coinbase.com");
  }
  if (cbChange.status === "fulfilled") change = cbChange.value;

  const missing = () => CODES.filter((c) => !(c in rates));

  if (missing().some((c) => c === "RUB" || c === "IDR")) {
    try {
      const fx = await getJSON("https://open.er-api.com/v6/latest/USD");
      for (const c of ["RUB", "IDR"]) if (!(c in rates)) rates[c] = fx.rates[c];
      sources.push("open.er-api.com");
    } catch { /* next fallback */ }
  }
  if (missing().some((c) => c === "BTC" || c === "ETH") || !Object.keys(change).length) {
    try {
      const cg = await getJSON("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true");
      if (!("BTC" in rates)) rates.BTC = 1 / cg.bitcoin.usd;
      if (!("ETH" in rates)) rates.ETH = 1 / cg.ethereum.usd;
      if (!Object.keys(change).length) change = { BTC: cg.bitcoin.usd_24h_change, ETH: cg.ethereum.usd_24h_change };
      sources.push("coingecko.com");
    } catch { /* next fallback */ }
  }

  if (missing().length) {
    return {
      mode: "demo",
      rates: DEMO_RATES,
      change_24h: { BTC: 1.84, ETH: -0.62 },
      updated_at: new Date().toISOString(),
      sources: ["примерные значения"],
    };
  }
  return { mode: "live", rates, change_24h: change, updated_at: new Date().toISOString(), sources };
}
