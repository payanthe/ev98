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
- صفحهٔ `/trip/`: انتخاب مبدأ و مقصد با جست‌وجو یا کلیک روی نقشه، برنامه‌ریزی توقف شارژ با مسیر و ماتریس فاصلهٔ نشان، و لینک قابل‌اشتراک که مکان‌ها، خودرو و شارژ فعلی را نگه می‌دارد

مستند تشخیص و ادغام رکوردهای تکراری، قواعد matching و فرمان‌های review در
[DUPLICATE_RECONCILIATION_FA.md](DUPLICATE_RECONCILIATION_FA.md) قرار دارد.

مستند استقرار production روی سرور (nginx، Docker، Certbot، DNS آروان) در
[DEPLOYMENT_FA.md](DEPLOYMENT_FA.md) است.

پرداخت، رزرو و حساب کاربری در این برش نیستند.

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
برنامه‌ریز سفر: <http://localhost:5173/trip/>

از دکمهٔ «منابع داده»، شارینت را به‌روزرسانی کنید. اولین اجرای کامل جزئیات چند ده ثانیه طول می‌کشد.

کلیدهای اختیاری را در `.env` بگذارید (نمونه در `.env.example`):

```bash
OCM_API_KEY=
ABRP_API_KEY=
NESHAN_API_KEY=
INGESTION_TOKEN=
```

کلید نشان فقط در بک‌اند استفاده می‌شود. برنامه‌ریز از Geocoding برای انتخاب مکان، Routing برای مسیر و Distance Matrix برای فاصلهٔ جاده‌ای بین ایستگاه‌ها استفاده می‌کند. برد عملی برای احتیاط ۷۵٪ برد ثبت‌شده و شارژ ذخیرهٔ رسیدن ۱۰٪ فرض می‌شود. در هر توقف فقط تا مقدار لازم برای رسیدن به نقطهٔ بعدی با این ذخیره شارژ می‌شود. زمان توقف شارژ از ظرفیت باتری، اختلاف شارژ ورود و خروج و توان سوکت سازگار برآورد می‌شود؛ توان متوسط ۷۵٪ توان مبنا و ۵ دقیقه آماده‌سازی برای هر توقف فرض می‌شود. اگر توان سوکت نامشخص باشد، ۵۰ کیلووات DC یا ۷ کیلووات AC و اگر سقف توان خودرو نامشخص باشد، ۸۰ کیلووات DC یا ۱۱ کیلووات AC فرض می‌شود. زمان کل سفر مجموع رانندگی و توقف‌های شارژ است و صف انتظار و منحنی شارژ اختصاصی خودرو را شامل نمی‌شود. نتیجه تخمینی است و در صورت محدودیت نرخ درخواست سوم نشان، خط نقشه مسیر کلی را نشان می‌دهد؛ مسافت بخش‌ها همچنان از ماتریس جاده‌ای محاسبه می‌شود.

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
- `GET /v1/trips/places?q=`
- `GET /v1/trips/reverse?lat=&lng=`
- `POST /v1/trips/plan`
- `POST /v1/ingestion/sync`
- `GET /health`

فیلترها: `connector`، `min_power_kw`، `source`، `availability`.
