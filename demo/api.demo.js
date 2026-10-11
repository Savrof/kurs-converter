// Demo data source for the single-file preview: no backend here, so try the
// public APIs straight from the browser and fall back to sample rates.
const DEMO_RATES = { USD: 1, RUB: 82.4, IDR: 16480, BTC: 1 / 112500, ETH: 1 / 4150 };

async function loadRates() {
  try {
    const [fx, cg] = await Promise.all([
      fetch("https://open.er-api.com/v6/latest/USD").then((r) => r.json()),
      fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true").then((r) => r.json()),
    ]);
    return {
      mode: "live",
      rates: { USD: 1, RUB: fx.rates.RUB, IDR: fx.rates.IDR, BTC: 1 / cg.bitcoin.usd, ETH: 1 / cg.ethereum.usd },
      change_24h: { BTC: cg.bitcoin.usd_24h_change, ETH: cg.ethereum.usd_24h_change },
      updated_at: new Date().toISOString(),
      sources: ["open.er-api.com", "coingecko.com"],
    };
  } catch {
    return {
      mode: "demo",
      rates: DEMO_RATES,
      change_24h: { BTC: 1.84, ETH: -0.62 },
      updated_at: new Date().toISOString(),
      sources: ["примерные значения"],
    };
  }
}
