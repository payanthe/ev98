# دیپلوی EV98 روی سرور

مستند استقرار production برای دامنهٔ [https://ev98.ir](https://ev98.ir) روی VPS اوبونتو با الگوی همین سرور: **nginx به‌عنوان ورودی عمومی**، اپ‌ها روی پورت لوکال، Docker فقط برای API و دیتابیس.

## معماری فعلی

```
اینترنت → nginx (:80/:443) → {
  static SPA   → /var/www/ev98
  /v1 /health  → 127.0.0.1:8098  (container api)
}
Docker:
  ev98-db-1   PostGIS  (فقط داخل شبکهٔ compose، پورت عمومی ندارد)
  ev98-api-1  FastAPI  (bind: 127.0.0.1:8098→8000)
```

| مسیر روی سرور | نقش |
|---|---|
| `/opt/ev98` | کد پروژه + compose + `.env.production` |
| `/var/www/ev98/current` | لینک به بیلد فعال فرانت |
| `/var/www/ev98/assets` | فایل‌های نام‌گذاری‌شده با هش از نسخه‌های فرانت |
| `/opt/ev98-data/offline-trip` | دادهٔ آفلاین نقشه، جست‌وجو، مسیریابی و ارتفاع |
| `/etc/nginx/sites-available/ev98.ir` | کانفیگ nginx |
| `/etc/letsencrypt/live/ev98.ir/` | گواهی Certbot |

پورت API روی `8098` انتخاب شده تا با سایت‌های دیگر همین سرور (`8000` sms، `8080` wisdom، …) تداخل نکند.

## پیش‌نیازها

- Ubuntu با `docker`، `docker compose`، `nginx`، `certbot`، Node.js 22.12 یا جدیدتر در سری ۲۲، `npm` و Python 3
- دامنه به IP سرور اشاره کند (**ابر آروان خاموش / DNS Only**)
- کلیدهای اختیاری OCM و ABRP در env

### DNS (آروان)

| نوع | نام | مقدار | ابر |
|---|---|---|---|
| A | `@` | IP سرور | **خاموش** |
| A | `www` | IP سرور | **خاموش** |

اگر ابر روشن باشد و SSL آروان خاموش، مرورگر خطای `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` می‌دهد. گواهی روی خود origin با Certbot است.

## فایل‌های مرتبط در ریپو

- `docker-compose.prod.yml` — db + api برای production
- `deploy/nginx-ev98.ir.conf` — نمونهٔ nginx (بعد از Certbot ممکن است بلوک SSL اضافه شود)
- `.env.production` — فقط روی سرور؛ در git نیست

## استقرار اولیه

### ۱) کپی کد

```bash
git clone https://github.com/payanthe/ev98.git /opt/ev98
mkdir -p /var/www/ev98 /opt/ev98-data/offline-trip
```

دادهٔ سفر را جدا از کد و مطابق [راهنمای آماده‌سازی داده](README.md#برنامهریز-سفر-آفلاین) آماده کنید.
از ماشین دارای داده، چهار مسیر زیر را منتقل کنید. پوشهٔ `elevation` برای محاسبهٔ شیب و نمایش نمودار لازم است.

```bash
rsync -a --progress \
  .offline-trip/iran.pmtiles .offline-trip/places.sqlite \
  .offline-trip/valhalla_tiles .offline-trip/elevation \
  root@SERVER:/opt/ev98-data/offline-trip/
```

برای تعویض دادهٔ یک نسخهٔ فعال، فایل‌های کامل را ابتدا در پوشه‌ای جدید آماده کنید و سپس مسیر آن را در `EV98_OFFLINE_TRIP_PATH` قرار دهید.

### ۲) محیط production

روی سرور فایل `/opt/ev98/.env.production` بسازید:

```bash
POSTGRES_PASSWORD=<رمز قوی>
CORS_ORIGINS=https://ev98.ir,https://www.ev98.ir
OCM_API_KEY=
ABRP_API_KEY=
SHARINET_BASE_URL=https://gen.emapna.com
STATUS_TTL_SECONDS=900
INGESTION_TOKEN=<توکن تصادفی برای sync>
EV98_OFFLINE_TRIP_PATH=/opt/ev98-data/offline-trip
```

```bash
chmod 600 /opt/ev98/.env.production
```

کاتالوگ خودرو از `outputs/emapna_ev_dataset/emapna_ev_normalized.csv` خوانده می‌شود و در compose به `/outputs` داخل کانتینر mount شده است.

### ۳) بالا آوردن API و DB

```bash
cd /opt/ev98
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build --wait
docker compose -f docker-compose.prod.yml --env-file .env.production ps
curl -fsS http://127.0.0.1:8098/v1/trips/ready
```

Migration با استارت API اجرا می‌شود. Compose وضعیت آمادگی نقشه، نمایهٔ جست‌وجو و گراف مسیر را از `/v1/trips/ready` می‌گیرد.

### ۴) بیلد فرانت

فایل وب‌فونت ایران‌یکان X را جدا از کد در `/opt/ev98-data/fonts/IRANYekanXVF.woff2` قرار دهید. همین فایل در نسخهٔ فعال همراه فرانت سرو می‌شود.

```bash
cd /opt/ev98
VITE_SITE_URL=https://ev98.ir python3 deploy/publish_frontend.py --web-root /var/www/ev98 \
  --font-file /opt/ev98-data/fonts/IRANYekanXVF.woff2
```

فرانت از مسیر نسبی `/v1/...` به API همان دامنه وصل می‌شود. اسکریپت ابتدا نسخه را می‌سازد و بعد لینک `current` را با یک عملیات عوض می‌کند. فایل‌های هش‌دار نسخه‌های قبلی برای تب‌های باز در دسترس می‌مانند.

### ۵) nginx

```bash
cp /opt/ev98/deploy/nginx-ev98.ir.conf /etc/nginx/sites-available/ev98.ir
ln -sfn /etc/nginx/sites-available/ev98.ir /etc/nginx/sites-enabled/ev98.ir
nginx -t && systemctl reload nginx
```

قبل از SSL فقط listen روی ۸۰ کافی است. بعد از Certbot بلوک ۴۴۳ و ریدایرکت HTTP→HTTPS اضافه می‌شود.

### ۶) SSL با Certbot

DNS باید به IP سرور رسیده باشد:

```bash
certbot --nginx -d ev98.ir -d www.ev98.ir --redirect
```

تمدید خودکار با `certbot.timer` فعال است. تست:

```bash
curl -sI https://ev98.ir/
curl -s https://ev98.ir/health
curl -sI https://www.ev98.ir/       # باید 301 به https://ev98.ir/ باشد
curl -sI https://ev98.ir/cars/      # باید text/html و 200 باشد
curl -sI https://ev98.ir/sitemap.xml # باید application/xml و 200 باشد
curl -s https://ev98.ir/robots.txt  # باید Sitemap را نشان دهد
```

### ۷) همگام‌سازی داده

بدون sync، نقشه خالی یا فقط بخشی از منابع را دارد. با توکن:

```bash
TOKEN=$(grep ^INGESTION_TOKEN= /opt/ev98/.env.production | cut -d= -f2-)

curl -s -X POST https://ev98.ir/v1/ingestion/sync \
  -H "Content-Type: application/json" \
  -H "X-Ingestion-Token: $TOKEN" \
  -d '{"source":"sharinet"}'

curl -s -X POST https://ev98.ir/v1/ingestion/sync \
  -H "Content-Type: application/json" \
  -H "X-Ingestion-Token: $TOKEN" \
  -d '{"source":"ocm"}'

curl -s -X POST https://ev98.ir/v1/ingestion/sync \
  -H "Content-Type: application/json" \
  -H "X-Ingestion-Token: $TOKEN" \
  -d '{"source":"abrp"}'

curl -s https://ev98.ir/v1/ingestion/sources | python3 -m json.tool
```

وضعیت هر منبع در `last_run` دیده می‌شود. شارینت معمولاً طولانی‌تر از OCM/ABRP است.

## به‌روزرسانی (deploy مجدد)

```bash
cd /opt/ev98 &&
git pull --ff-only &&
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build --wait &&
curl -fsS http://127.0.0.1:8098/v1/trips/ready &&
VITE_SITE_URL=https://ev98.ir python3 deploy/publish_frontend.py --web-root /var/www/ev98 \
  --font-file /opt/ev98-data/fonts/IRANYekanXVF.woff2
```

در اولین انتشار با ساختار `current`، پس از ساخت موفق فرانت، نسخهٔ جدید کانفیگ nginx را نصب کنید و با `nginx -t && systemctl reload nginx` فعال کنید. Volume دیتابیس `ev98_pg` در به‌روزرسانی عادی حفظ می‌شود.

## دستورات مفید

```bash
# لاگ API
docker logs -f ev98-api-1

# وضعیت کانتینرها
docker compose -f /opt/ev98/docker-compose.prod.yml ps

# ری‌استارت فقط API
docker compose -f /opt/ev98/docker-compose.prod.yml restart api

# تست لوکال با Host
curl -sI -H "Host: ev98.ir" http://127.0.0.1/
curl -sk --resolve ev98.ir:443:127.0.0.1 https://ev98.ir/health
```

## عیب‌یابی رایج

| علامت | علت محتمل | کار |
|---|---|---|
| `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` | DNS هنوز به IP پارکینگ/CDN قدیمی می‌رود یا ابر آروان روشن است | رکورد A فقط IP سرور، ابر خاموش؛ کش DNS مک/کروم |
| سایت ۲۰۰ است ولی نقشه خالی | sync نشده | sync سه منبع بالا |
| `/v1/vehicles/` خطای ۵۰۰ | CSV خودرو mount نیست | وجود `outputs/.../emapna_ev_normalized.csv` و volume در compose |
| پورت درگیر | تداخل با سرویس دیگر | API روی `127.0.0.1:8098` بماند |
| Certbot برای `www` fail | رکورد DNS برای www نیست | A برای `www` بسازید بعد `certbot --nginx -d ev98.ir -d www.ev98.ir --expand` |

### پاک کردن کش DNS روی مک

```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

در کروم: `chrome://net-internals/#dns` → Clear host cache و `chrome://net-internals/#sockets` → Flush socket pools.

چک:

```bash
dig +short ev98.ir A
# باید فقط IP سرور باشد
```

## نکات امنیتی

- `.env` / `.env.production` را commit نکنید؛ روی سرور `chmod 600`
- پورت API و DB را روی `0.0.0.0` باز نکنید
- `INGESTION_TOKEN` را خالی نگذارید تا endpointهای sync عمومی نشوند
- پسورد root سرور را در چت/مستند نگه ندارید؛ ترجیحاً SSH key

## ارتباط با توسعهٔ محلی

برای توسعه از `docker-compose.yml` (db روی `5433`، vite روی `5173`) استفاده کنید. `docker-compose.prod.yml` مخصوص VPS است و فرانت را با nginx استاتیک سرو می‌کند، نه با `vite dev`.
