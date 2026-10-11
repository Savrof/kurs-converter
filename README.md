# Kurs: конвертер RUB · IDR · BTC · ETH

Конвертер между рублём, индонезийской рупией, биткоином и эфиром по актуальным курсам.
Бэкенд на Python (FastAPI) собирает курсы из открытых API и кэширует их. UI написан на React (Vite).

## Источники курсов

| Что | Источник | Ключ API |
|---|---|---|
| RUB, IDR к USD | [open.er-api.com](https://www.exchangerate-api.com/docs/free) | не нужен |
| BTC, ETH к USD + изменение за 24 ч | [CoinGecko](https://www.coingecko.com/en/api) `/simple/price` | не нужен |
| Запасной для всех четырёх | [fawazahmed0/currency-api](https://github.com/fawazahmed0/exchange-api) через jsDelivr | не нужен |

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
