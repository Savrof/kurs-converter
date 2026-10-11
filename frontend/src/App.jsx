import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { loadRates } from "./api";

const CURRENCIES = [
  { code: "RUB", name: "Российский рубль", sign: "₽", decimals: 2, kind: "fiat" },
  { code: "USD", name: "Доллар США", sign: "$", decimals: 2, kind: "fiat" },
  { code: "IDR", name: "Индонезийская рупия", sign: "Rp", decimals: 0, kind: "fiat" },
  { code: "BTC", name: "Bitcoin", sign: "₿", decimals: 8, kind: "crypto" },
  { code: "ETH", name: "Ethereum", sign: "Ξ", decimals: 6, kind: "crypto" },
];
const BY_CODE = Object.fromEntries(CURRENCIES.map((c) => [c.code, c]));
const REFRESH_MS = 60_000;

function parseAmount(text) {
  const n = Number(String(text).replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? n : null;
}

// Fixed decimals per currency, but never round a small non-zero value down to "0".
function fmt(value, code) {
  if (value == null || !Number.isFinite(value)) return "—";
  const d = BY_CODE[code]?.decimals ?? 2;
  if (value !== 0 && Math.abs(value) < Math.pow(10, -d)) {
    return value.toLocaleString("ru-RU", { maximumSignificantDigits: 4 });
  }
  const digits = value !== 0 && Math.abs(value) < 1 && d === 0 ? 4 : d;
  return value.toLocaleString("ru-RU", { minimumFractionDigits: Math.min(digits, 2), maximumFractionDigits: digits });
}

// Rates in the matrix: keep ~6 significant digits so 0.0000105 and 9 500 000 both read well.
function fmtRate(value) {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return value.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
  if (Math.abs(value) >= 1) return value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  return value.toLocaleString("ru-RU", { maximumSignificantDigits: 4 });
}

// Copied text drops the thousands separators so it pastes into calculators and
// spreadsheets as a number: "9 156 420,5" -> "9156420,5".
const forClipboard = (text) => String(text).replace(/[\s\u00a0\u202f]/g, "");

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Older browsers and some embedded views refuse the async clipboard API.
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

function Copy({ id, text, copied, onCopy, className = "", children }) {
  const value = forClipboard(text);
  return (
    <button
      type="button"
      className={`copy ${className}`}
      onClick={() => onCopy(id, value)}
      title="Нажмите, чтобы скопировать"
      aria-label={`Скопировать ${value}`}
      data-copied={copied?.id === id && copied.ok ? "" : undefined}
    >
      {children ?? text}
    </button>
  );
}

function timeAgo(date, now) {
  const s = Math.max(0, Math.round((now - date) / 1000));
  if (s < 60) return `${s} с назад`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} мин назад`;
  return date.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Banknote-style guilloche rosette, drawn once per theme change.
function Guilloche() {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);
      const color = getComputedStyle(canvas).color;
      ctx.strokeStyle = color;
      ctx.lineWidth = 0.6;
      const cx = width - 120, cy = height / 2;
      for (let ring = 0; ring < 6; ring++) {
        const R = 70 + ring * 22, r = 9 + ring * 2, d = 26 + ring * 4;
        ctx.globalAlpha = 0.5 - ring * 0.06;
        ctx.beginPath();
        for (let t = 0; t <= Math.PI * 2 * r; t += 0.02) {
          const x = (R - r) * Math.cos(t) + d * Math.cos(((R - r) / r) * t);
          const y = (R - r) * Math.sin(t) - d * Math.sin(((R - r) / r) * t);
          t === 0 ? ctx.moveTo(cx + x, cy + y) : ctx.lineTo(cx + x, cy + y);
        }
        ctx.stroke();
      }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener?.("change", draw);
    return () => { ro.disconnect(); mq.removeEventListener?.("change", draw); };
  }, []);
  return <canvas ref={ref} className="guilloche" aria-hidden="true" />;
}

function CurrencyPicker({ id, value, onChange, exclude }) {
  return (
    <div className="picker" role="radiogroup" aria-labelledby={id}>
      {CURRENCIES.map((c) => (
        <button
          key={c.code}
          type="button"
          role="radio"
          aria-checked={value === c.code}
          className={`chip chip--${c.code.toLowerCase()}`}
          onClick={() => onChange(c.code)}
          title={c.name}
          data-dim={exclude === c.code ? "" : undefined}
        >
          <span className="chip__sign">{c.sign}</span>
          {c.code}
        </button>
      ))}
    </div>
  );
}

function Change({ value }) {
  if (value == null) return null;
  const up = value >= 0;
  return (
    <span className={`delta ${up ? "delta--up" : "delta--down"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}% за 24 ч
    </span>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [amountText, setAmountText] = useState("0,05");
  const [from, setFrom] = useState("BTC");
  const [to, setTo] = useState("RUB");
  const [copied, setCopied] = useState(null);
  const copyTimer = useRef(null);

  const onCopy = useCallback(async (id, text) => {
    const ok = await copyText(text);
    setCopied({ id, text, ok });
    clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopied(null), 1800);
  }, []);

  const refresh = useCallback(async (force = false) => {
    setLoading(true);
    try {
      setData(await loadRates(force));
      setError(null);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(() => refresh(), REFRESH_MS);
    const clock = setInterval(() => setNow(Date.now()), 5_000);
    return () => { clearInterval(t); clearInterval(clock); };
  }, [refresh]);

  const rates = data?.rates;
  const amount = parseAmount(amountText);
  const conv = useCallback((v, a, b) => (rates ? (v * rates[b]) / rates[a] : null), [rates]);
  const result = amount != null ? conv(amount, from, to) : null;
  const updated = data ? new Date(data.updated_at) : null;
  const stale = updated && now - updated > 10 * 60_000;

  const pickFrom = (c) => { if (c === to) setTo(from); setFrom(c); };
  const pickTo = (c) => { if (c === from) setFrom(to); setTo(c); };
  const swap = () => {
    setFrom(to);
    setTo(from);
    if (result != null) setAmountText(fmt(result, to).replace(/\s/g, ""));
  };

  const others = useMemo(() => CURRENCIES.filter((c) => c.code !== from), [from]);

  return (
    <div className="page">
      <header className="masthead">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">₽⇄₿</span>
          <div>
            <h1>Kurs</h1>
            <p className="brand__sub">Рубль, доллар, рупия, биткоин и эфир по текущему курсу</p>
          </div>
        </div>
        <div className="status">
          <span className={`pill pill--${error && !data ? "err" : data?.mode === "demo" ? "demo" : stale ? "stale" : "live"}`}>
            <span className="pill__dot" />
            {error && !data ? "нет данных" : data?.mode === "demo" ? "демо-курсы" : stale ? "устарело" : "онлайн"}
          </span>
          <button type="button" className="btn-ghost" onClick={() => refresh(true)} disabled={loading} id="refresh">
            {loading ? "Обновляю…" : "Обновить"}
          </button>
        </div>
      </header>

      <section className="ticket" aria-label="Конвертер">
        <Guilloche />
        <div className="ticket__row">
          <label className="label" id="from-label" htmlFor="amount">Отдаю</label>
          <CurrencyPicker id="from-label" value={from} onChange={pickFrom} />
          <div className="amount">
            <input
              id="amount"
              inputMode="decimal"
              autoComplete="off"
              value={amountText}
              onChange={(e) => setAmountText(e.target.value)}
              aria-invalid={amount == null}
            />
            <span className="amount__code">{from}</span>
          </div>
          {amount == null && <p className="hint hint--err">Введите число, например 1500 или 0,25</p>}
        </div>

        <button type="button" className="swap" onClick={swap} aria-label="Поменять валюты местами"><span aria-hidden="true">⇅</span></button>

        <div className="ticket__row">
          <span className="label" id="to-label">Получаю</span>
          <CurrencyPicker id="to-label" value={to} onChange={pickTo} />
          <output className="result" htmlFor="amount" aria-live="polite">
            <Copy id="result" text={fmt(result, to)} copied={copied} onCopy={onCopy} className="result__value" />
            <span className="amount__code">{to}</span>
          </output>
          {to === "BTC" && result != null && result < 0.01 && (
            <p className="hint">≈ {Math.round(result * 1e8).toLocaleString("ru-RU")} sat</p>
          )}
        </div>

        <div className="ticket__foot">
          <span>1 {from} = <Copy id="rate-fwd" text={fmtRate(conv(1, from, to))} copied={copied} onCopy={onCopy} className="rate" /> {to}</span>
          <span>1 {to} = <Copy id="rate-back" text={fmtRate(conv(1, to, from))} copied={copied} onCopy={onCopy} className="rate" /> {from}</span>
        </div>
      </section>

      <section aria-labelledby="all-h">
        <h2 id="all-h" className="section-h">
          {amount != null ? fmt(amount, from) : "—"} {from} во всех валютах
        </h2>
        <p className="hint copy-hint">Нажмите на любое число, чтобы скопировать его</p>
        <div className="tiles">
          {others.map((c) => {
            const value = amount != null ? fmt(conv(amount, from, c.code), c.code) : "—";
            return (
              <Copy key={c.code} id={`tile-${c.code}`} text={value} copied={copied} onCopy={onCopy} className={`tile tile--${c.code.toLowerCase()}`}>
                <span className="tile__code">{c.sign} {c.code}</span>
                <span className="tile__value">{value}</span>
                <span className="tile__name">{c.name}</span>
              </Copy>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="mx-h">
        <h2 id="mx-h" className="section-h">Кросс-курсы</h2>
        <div className="matrix-wrap">
          <table className="matrix">
            <thead>
              <tr>
                <th scope="col">1 единица</th>
                {CURRENCIES.map((c) => <th scope="col" key={c.code}>в {c.code}</th>)}
              </tr>
            </thead>
            <tbody>
              {CURRENCIES.map((r) => (
                <tr key={r.code}>
                  <th scope="row">
                    <span className={`dot dot--${r.code.toLowerCase()}`} />1 {r.code}
                    {r.kind === "crypto" && <Change value={data?.change_24h?.[r.code]} />}
                  </th>
                  {CURRENCIES.map((c) => (
                    <td key={c.code} className={r.code === c.code ? "same" : ""}>
                      {r.code === c.code ? "1" : (
                        <Copy id={`mx-${r.code}-${c.code}`} text={fmtRate(conv(1, r.code, c.code))} copied={copied} onCopy={onCopy} />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="foot">
        {error && <p className="hint hint--err">Не удалось обновить курсы: {error}. Показаны последние полученные данные.</p>}
        {data?.mode === "demo" && (
          <p className="hint">
            Живые API недоступны в этом окне, поэтому показаны примерные курсы. В полной версии курсы приходят с бэкенда на Python.
          </p>
        )}
        <p>
          Обновлено {updated ? timeAgo(updated, now) : "—"} · источники: {data?.sources?.join(", ") || "—"} · автообновление раз в минуту
        </p>
      </footer>

      <div className="toast" role="status" aria-live="polite" hidden={!copied}>
        {copied && (copied.ok ? <>Скопировано: <b>{copied.text}</b></> : "Не получилось скопировать. Выделите число и нажмите Ctrl+C")}
      </div>
    </div>
  );
}
