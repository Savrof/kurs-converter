# Kurs: конвертер RUB · USD · IDR · BTC · ETH

Конвертер между рублём, долларом США, индонезийской рупией, биткоином и эфиром по актуальным курсам.
Бэкенд на Python (FastAPI) собирает курсы из открытых API и кэширует их. UI написан на React (Vite).

## Источники курсов

Правило проекта: **метка времени никогда не выдумывается**. Каждый курс несёт
собственное время провайдера, а если провайдер его не сообщает, так и написано —
«без метки времени». Индикатор в шапке показывает свежесть по этим меткам, а не
факт того, что наш запрос прошёл.

| Что | Источник | Метка времени | Ключ API |
|---|---|---|---|
| BTC, ETH | [Coinbase Exchange](https://docs.cdp.coinbase.com/exchange/reference) `/products/{BTC,ETH}-USD/ticker` | да, время сделки | не нужен |
| BTC, ETH (запасной) | [CoinGecko](https://www.coingecko.com/en/api) `/simple/price` | да, `last_updated_at` | не нужен |
| RUB, IDR | [open.er-api.com](https://www.exchangerate-api.com/docs/free) | да, но фиксинг раз в сутки | не нужен |
| RUB, IDR (запасной) | [Coinbase](https://docs.cdp.coinbase.com/coinbase-business/track-apis/exchange-rates) `/v2/exchange-rates` | **нет** | не нужен |
| RUB официальный | [ЦБ РФ](https://www.cbr-xml-daily.ru/) | да, дата фиксинга | не нужен |

Рыночный и официальный курс рубля показываются рядом и подписаны: единого
«настоящего» курса рубля не существует, расхождение в 1–2% между источниками —
норма. Таблица Coinbase по фиату отодвинута в запасные: она не сообщает времени
и расходилась с рынком примерно на 1%.

Все курсы хранятся как «единиц валюты за 1 USD», поэтому любая пара считается
через доллар. Кэш живёт 60 секунд (`RATES_TTL`). Если провайдер упал, отдаются
последние полученные данные.

**Это справочные курсы.** Для крупной суммы цену назначает банк или биржа со
своим спредом, а не справочник: ни этот конвертер, ни Google не являются
котировкой, по которой вам проведут сделку.

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
