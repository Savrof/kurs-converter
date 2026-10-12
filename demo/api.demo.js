// Data source for the single-file build (GitHub Pages and the artifact demo).
// No backend here, so the browser asks the public APIs directly.
//
// Rule of this file: a timestamp is never invented. Every rate carries the
// provider's own "as of" time, or null when the provider states none, and the
// UI reports that honestly instead of showing the moment we made the request.

const CODES = ["RUB", "IDR", "BTC", "ETH"];
const DEMO_RATES = { USD: 1, RUB: 82.4, IDR: 16480, BTC: 1 / 112500, ETH: 1 / 4150 };

const getJSON = async (url, ms = 7000) => {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms);
  try {
    const r = await fetch(url, { signal: ac.signal });
    if (!r.ok) throw new Error(`${new URL(url).host} ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
};

// Coinbase Exchange: last traded price plus the exchange's own timestamp.
async function cryptoFromCoinbase() {
  const one = async (code) => {
    const t = await getJSON(`https://api.exchange.coinbase.com/products/${code}-USD/ticker`);
    const price = Number(t.price);
    if (!price) throw new Error(`${code}: no price`);
    return [code, { perUsd: 1 / price, asOf: t.time || null, src: "Coinbase Exchange" }];
  };
  return Object.fromEntries(await Promise.all(["BTC", "ETH"].map(one)));
}

async function changeFromCoinbase() {
  const one = async (code) => {
    const s = await getJSON(`https://api.exchange.coinbase.com/products/${code}-USD/stats`);
    return [code, ((s.last - s.open) / s.open) * 100];
  };
  return Object.fromEntries(await Promise.all(["BTC", "ETH"].map(one)));
}

// Coinbase's reference table covers fiat, but carries no timestamp of its own and
// has been seen ~1% off the market, so it is only a fallback for RUB/IDR.
async function fiatFromCoinbase() {
  const d = await getJSON("https://api.coinbase.com/v2/exchange-rates?currency=USD");
  const out = {};
  for (const c of ["RUB", "IDR"]) {
    const v = Number(d.data.rates[c]);
    if (v) out[c] = { perUsd: v, asOf: null, src: "Coinbase" };
  }
  return out;
}

// ExchangeRate-API: a once-a-day fixing that does state when it was made.
async function fromErApi() {
  const d = await getJSON("https://open.er-api.com/v6/latest/USD");
  if (d.result !== "success") throw new Error(`er-api: ${d["error-type"]}`);
  const asOf = d.time_last_update_unix ? new Date(d.time_last_update_unix * 1000).toISOString() : null;
  const out = {};
  for (const c of ["RUB", "IDR"]) {
    if (d.rates[c]) out[c] = { perUsd: d.rates[c], asOf, src: "open.er-api.com" };
  }
  return out;
}

async function fromCoinGecko() {
  const d = await getJSON(
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true&include_last_updated_at=true"
  );
  const rates = {};
  const change = {};
  for (const [code, id] of [["BTC", "bitcoin"], ["ETH", "ethereum"]]) {
    rates[code] = {
      perUsd: 1 / d[id].usd,
      asOf: d[id].last_updated_at ? new Date(d[id].last_updated_at * 1000).toISOString() : null,
      src: "CoinGecko",
    };
    if (d[id].usd_24h_change != null) change[code] = d[id].usd_24h_change;
  }
  return { rates, change };
}

// Bank of Russia official rate: the legal reference rate, published once a day.
async function officialRub() {
  const d = await getJSON("https://www.cbr-xml-daily.ru/daily_json.js");
  const v = d.Valute?.USD;
  if (!v?.Value) throw new Error("cbr: no USD");
  return { rate: v.Value, prev: v.Previous ?? null, asOf: d.Date || null, src: "ЦБ РФ" };
}

async function loadRates() {
  const rates = { USD: 1 };
  const meta = {};
  const official = {};
  let change = {};

  const take = (got) => {
    for (const [code, v] of Object.entries(got)) {
      if (!(code in rates)) {
        rates[code] = v.perUsd;
        meta[code] = { src: v.src, asOf: v.asOf };
      }
    }
  };
  const missing = () => CODES.filter((c) => !(c in rates));

  const [crypto, fiat, cbr, stats] = await Promise.allSettled([
    cryptoFromCoinbase(),
    fromErApi(),
    officialRub(),
    changeFromCoinbase(),
  ]);
  if (crypto.status === "fulfilled") take(crypto.value);
  if (fiat.status === "fulfilled") take(fiat.value);
  if (stats.status === "fulfilled") change = stats.value;
  if (cbr.status === "fulfilled") official.RUB = cbr.value;

  if (missing().some((c) => c === "RUB" || c === "IDR")) {
    try {
      take(await fiatFromCoinbase());
    } catch { /* next fallback */ }
  }
  if (missing().some((c) => c === "BTC" || c === "ETH") || !Object.keys(change).length) {
    try {
      const cg = await fromCoinGecko();
      take(cg.rates);
      if (!Object.keys(change).length) change = cg.change;
    } catch { /* next fallback */ }
  }
  // Nothing else answered for the rouble: the official rate can stand in, labelled as such.
  if (!("RUB" in rates) && official.RUB) {
    rates.RUB = official.RUB.rate;
    meta.RUB = { src: "ЦБ РФ (официальный)", asOf: official.RUB.asOf };
  }

  if (missing().length) {
    return {
      mode: "demo",
      rates: DEMO_RATES,
      meta: {},
      official,
      change_24h: { BTC: 1.84, ETH: -0.62 },
      fetched_at: new Date().toISOString(),
    };
  }
  return { mode: "live", rates, meta, official, change_24h: change, fetched_at: new Date().toISOString() };
}
