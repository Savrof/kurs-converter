# Kurs: конвертер RUB · USD · IDR · BTC · ETH

Конвертер между рублём, долларом США, индонезийской рупией, биткоином и эфиром по актуальным курсам.
Бэкенд на Python (FastAPI) собирает курсы из открытых API и кэширует их. UI написан на React (Vite).

## Источники курсов

Основной источник: Coinbase, у него же берёт курсы криптовалют конвертер Google. Один запрос возвращает и фиат, и крипту, курсы обновляются в течение дня. Остальные источники подставляются, только если Coinbase не ответил или не вернул какую-то валюту.

| Порядок | Что | Источник | Ключ API |
|---|---|---|---|
| 1 | Все валюты | [Coinbase](https://docs.cdp.coinbase.com/coinbase-app/docs/api-exchange-rates) `/v2/exchange-rates` | не нужен |
| 1 | Изменение BTC и ETH за 24 ч | Coinbase Exchange `/products/{BTC,ETH}-USD/stats` | не нужен |
| 2 | RUB, IDR | [open.er-api.com](https://www.exchangerate-api.com/docs/free) (обновляется раз в сутки) | не нужен |
| 2 | BTC, ETH | [CoinGecko](https://www.coingecko.com/en/api) `/simple/price` | не нужен |
| 3 | Все валюты | [fawazahmed0/currency-api](https://github.com/fawazahmed0/exchange-api) через jsDelivr | не нужен |

Все курсы хранятся как «единиц валюты за 1 USD», поэтому любая пара считается через доллар.
Кэш живёт 60 секунд (`RATES_TTL`). Если провайдер упал, отдаются последние полученные данные.

## Запуск

```bash
# бэкенд
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000/docs

# фронтенд (в другом терминале)
cd frontend
npm install
npm run dev                            # http://localhost:5173, /api проксируется на :8000
```

Продакшен одним процессом: `cd frontend && npm run build`, после чего FastAPI сам раздаёт `frontend/dist` на `/`.

## API

- `GET /api/rates[?refresh=true]` возвращает `{base, rates, change_24h, updated_at, sources}`
- `GET /api/convert?amount=0.05&from=BTC&to=RUB` возвращает `{result, rate, updated_at, ...}`
- `GET /api/health`

## Тесты

```bash
cd backend && pytest
```

## Демо одним файлом

`python tools/build_demo.py` собирает `demo/kurs-demo.html` и `index.html` в корне (для GitHub Pages): тот же `App.jsx`, но без бэкенда.
Курсы берутся напрямую из публичных API в браузере, а если они недоступны, показываются примерные значения с пометкой «демо-курсы».

GitHub Pages: Settings → Pages → Deploy from a branch → `main` / `(root)`. Демо откроется на `https://savrof.github.io/kurs-converter/`.
