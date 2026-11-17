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
- صفحهٔ `/trip/`: انتخاب مبدأ و مقصد با جست‌وجو یا کلیک روی نقشه، مسیر و توقف‌های شارژ با دادهٔ آفلاین، و لینک قابل‌اشتراک که مکان‌ها، خودرو و شارژ فعلی را نگه می‌دارد

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
INGESTION_TOKEN=
```

### برنامه‌ریز سفر آفلاین

صفحهٔ `/trip/` نقشهٔ برداری، جست‌وجوی مکان، مسیریابی خودرو و ماتریس فاصلهٔ جاده‌ای را از داده‌های محلی می‌خواند. مرورگر کاشی‌های مورد نیاز را از API خود EV98 با درخواست‌های Range می‌گیرد. فایل فونت و موتور نمایش همراه فرانت‌اند سرو می‌شوند. دستورهای گردش از مسیر نهاییِ عبوری از توقف‌ها ساخته می‌شوند. جست‌وجو نام شهرها، معبرها و مکان‌های ثبت‌شده در OSM را پوشش می‌دهد و نشانی پین را از نزدیک‌ترین نام ثبت‌شده تخمین می‌زند.

سه جزء را در `.offline-trip/` ریشهٔ پروژه قرار دهید. برای مسیر دلخواه در اجرای مستقیم بک‌اند، `OFFLINE_TRIP_DIR` را به مسیر مطلق تنظیم کنید.

- `valhalla_tiles/` گراف Valhalla از [برش OpenStreetMap ایران در Geofabrik](https://download.geofabrik.de/asia/iran.html). گراف آزمایش ارتفاع قبلی در `outputs/elevation-pilot/data/valhalla_tiles/` قابل استفاده است.
- `places.sqlite` نمایهٔ جست‌وجو و موقعیت. با فایل PBF گراف، دستور زیر را از ریشهٔ پروژه اجرا کنید.
- `iran.pmtiles` نقشهٔ پایهٔ [Protomaps](https://docs.protomaps.com/basemaps/downloads) با پوشش ایران تا زوم دادهٔ ۱۵. ابتدا آن را در یک فایل موقت بسازید و پس از اتمام، به نام نهایی جابه‌جا کنید.

```bash
mkdir -p .offline-trip
uv run --python 3.12 scripts/build_trip_places.py /path/to/iran.osm.pbf .offline-trip/places.sqlite
pmtiles extract https://build.protomaps.com/20261116.pmtiles .offline-trip/iran.download.pmtiles \
  --bbox=43.5,24.75,63.65,40.15 --maxzoom=15
pmtiles verify .offline-trip/iran.download.pmtiles
mv .offline-trip/iran.download.pmtiles .offline-trip/iran.pmtiles
```

برای ساخت گراف از نو، از محیط پایتون بک‌اند استفاده کنید.

```bash
mkdir -p .offline-trip/valhalla_tiles
backend/.venv/bin/python -c 'import json; from valhalla import get_config; print(json.dumps(get_config(tile_dir=".offline-trip/valhalla_tiles", tile_extract="")))' > .offline-trip/valhalla.json
backend/.venv/bin/python -m valhalla valhalla_build_tiles -c .offline-trip/valhalla.json /path/to/iran.osm.pbf
```

پس از آماده‌سازی داده‌ها، `docker compose up --build` نقشه و گراف را از پوشهٔ محلی در اختیار API می‌گذارد. برای اجرای مستقیم فرانت‌اند و بک‌اند، همان تنظیمات اجرای لوکال بالا کافی است. دریافت اولیهٔ داده و نصب وابستگی‌ها یک‌بار به اینترنت نیاز دارند.

برد عملی خودرو ۷۵٪ برد ثبت‌شده و ذخیرهٔ رسیدن ۱۰٪ است. زمان رانندگی برآورد آفلاین بدون ترافیک زنده است. زمان شارژ بر اساس ظرفیت باتری، اختلاف شارژ و ۷۵٪ توان سوکت سازگار، به‌علاوهٔ ۵ دقیقه آماده‌سازی برای هر توقف، محاسبه می‌شود. برای توان نامشخص سوکت ۵۰ کیلووات DC یا ۷ کیلووات AC و برای سقف توان نامشخص خودرو ۸۰ کیلووات DC یا ۱۱ کیلووات AC فرض می‌شود. صف انتظار و منحنی شارژ اختصاصی خودرو در این زمان لحاظ نمی‌شوند.

### ارتفاع و انرژی مسیر

برای نصب کاشی‌های سراسری [Copernicus GLO‑90](https://registry.opendata.aws/copernicus-dem/) از همان فایل PBF استفاده کنید که گراف Valhalla از آن ساخته شده است. اسکریپت محدودهٔ راه‌ها را از فایل محلی می‌خواند و در پایان فهرست کاشی‌ها را ثبت می‌کند.

```bash
uv run --python 3.12 scripts/build_iran_elevation.py /path/to/iran.osm.pbf .offline-trip/elevation
```

موتور روی مسیر تقریباً هر ۳۰ متر نمونه می‌گیرد. اگر GLO‑30 تمام بخش را پوشش دهد، از آن و پنجرهٔ هموارسازی ۱۵۰ متر استفاده می‌کند. در بقیهٔ مسیرها، کاشی‌های ۹۰ متری با پنجرهٔ ۲۷۰ متر به کار می‌روند. اصلاح شیب با جرم فرضی ۱۸۵۰ کیلوگرم و سرعت متوسط بخش طبق Valhalla به مصرف پایهٔ هر خودرو اضافه می‌شود. برنامه‌ریز ذخیرهٔ ۱۰٪ را در طول بخش بررسی می‌کند و بازیابی انرژی را در ظرفیت کامل باتری محدود می‌کند.

نمودار صفحهٔ سفر ارتفاع، شارژ باتری، انرژی مصرفی و انرژی بازیابی‌شده را روی محور مشترک مسافت نمایش می‌دهد. شیب کمتر از ۱٪ هموار محسوب می‌شود. بخش فاقد پوشش با مدل مسافت برآورد و در نمودار مشخص می‌شود. اختلاف ارتفاع ۱۲ متر یا بیشتر میان نمونهٔ مرکز و نمونه‌های ۱۵ متر دو طرف راه، بخش را مشکوک می‌کند. مدل در آن بخش فقط جهش‌های ارتفاع مسیر را با روند طولی همسایه‌ها بررسی می‌کند. پل و تونل از برچسب لبه‌های همان مسیر در Valhalla شناخته می‌شوند و از ارتفاع مسیر قبل و بعد سازه برآورد می‌شوند. با یک سمت قابل استفاده، پروفایل داخل سازه هموار فرض می‌شود. نشانگرهای کیفیت روی محور مسافت جای بخش‌های مشکوک و سازه‌های تخمینی را مشخص می‌کنند. روی نقشه می‌توانید بین جریان باتری و شیب مسیر جابه‌جا شوید. سبز نشان‌دهندهٔ افزایش خالص شارژ حین حرکت و آبی نشان‌دهندهٔ مصرف خالص است. در نمای شیب، رنگ گرم سربالایی و آبی سرپایینی را مشخص می‌کند. انتخاب هر مورد از راهنمای رنگ، نقشه را روی یک بخش از همان نوع متمرکز می‌کند. برای مقایسه با فرض مسیر هموار، در `POST /v1/trips/plan` مقدار `include_grade` را `false` بفرستید.

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
