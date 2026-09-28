# EV98

نسخهٔ اولیهٔ پلتفرم نقشهٔ شارژ خودروی برقی. این برش، فاز «دادهٔ ملی و نقشه» از سند معماری است: چند منبع ingest می‌شوند، payload خام حفظ می‌شود، و نقشه فقط از API خود پلتفرم می‌خواند.

## همین نسخه چه دارد

- بک‌اند FastAPI با PostgreSQL/PostGIS
- سه adapter: شارینت (بدون کلید)، Open Charge Map و ABRP (با کلید)
- تفکیک charge point شارینت از Location؛ خوشه‌بندی هم‌نام‌های نزدیک‌تر از ۲۵۰ متر
- پیوند صریح ABRP با `source=ocm` به همان مکان OCM، بدون ساخت مکان تکراری
- اولویت فیلد: مختصات شارینت مختصات ضعیف‌تر را بازنویسی نمی‌کند
- وضعیت زنده با TTL پانزده‌دقیقه‌ای؛ بعد از انقضا روی نقشه «منقضی» است، نه آزاد
- قیمت شارینت به ریال (کوچک‌ترین واحد) ذخیره و به تومان نمایش داده می‌شود
- فرانت React: نقشه، فیلتر، جست‌وجو و پنل جزئیات

مستند تشخیص و ادغام رکوردهای تکراری، قواعد matching و فرمان‌های review در
[DUPLICATE_RECONCILIATION_FA.md](DUPLICATE_RECONCILIATION_FA.md) قرار دارد.

مستند استقرار production روی سرور (nginx، Docker، Certbot، DNS آروان) در
[DEPLOYMENT_FA.md](DEPLOYMENT_FA.md) است.

پرداخت، رزرو، حساب کاربری و مسیریابی خودروی برقی در این برش نیستند.

## اجرا

PostgreSQL باید با PostGIS بالا باشد. Compose پایگاه را روی پورت `5433` منتشر می‌کند تا با Postgres محلیِ پورت `5432` تداخل نکند:

```bash
docker compose up -d db
cd backend
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

در ترمینال دیگر:

```bash
cd frontend
npm install
npm run dev
```

نقشه: <http://localhost:5173>

از دکمهٔ «منابع داده»، شارینت را به‌روزرسانی کنید. اولین اجرای کامل جزئیات چند ده ثانیه طول می‌کشد.

کلیدهای اختیاری را در `.env` بگذارید (نمونه در `.env.example`):

```bash
OCM_API_KEY=
ABRP_API_KEY=
INGESTION_TOKEN=
```

اگر `INGESTION_TOKEN` خالی نباشد، درخواست sync باید هدر `X-Ingestion-Token` داشته باشد.

همگام‌سازی از ترمینال:

```bash
cd backend
uv run python -m app.cli sync sharinet
```

## API

- `GET /v1/locations/?bbox=south,west,north,east`
- `GET /v1/locations/?lat=&lng=&radius_m=`
- `GET /v1/locations/?q=`
- `GET /v1/locations/{id}`
- `GET /v1/ingestion/sources`
- `POST /v1/ingestion/sync`
- `GET /health`

فیلترها: `connector`، `min_power_kw`، `source`، `availability`.
