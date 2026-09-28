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
| `/var/www/ev98` | بیلد استاتیک فرانت |
| `/etc/nginx/sites-available/ev98.ir` | کانفیگ nginx |
| `/etc/letsencrypt/live/ev98.ir/` | گواهی Certbot |

پورت API روی `8098` انتخاب شده تا با سایت‌های دیگر همین سرور (`8000` sms، `8080` wisdom، …) تداخل نکند.

## پیش‌نیازها

- Ubuntu با `docker`، `docker compose`، `nginx`، `certbot`، `nodejs`/`npm`
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
mkdir -p /opt/ev98 /var/www/ev98
# از ماشین توسعه:
rsync -az --delete \
  --exclude '.git' --exclude 'node_modules' --exclude '.venv' \
  --exclude 'frontend/dist' --exclude '.agents' --exclude '.obsidian' \
  ./ root@SERVER:/opt/ev98/
```

یا `git clone` از GitHub و ساخت `.env.production` روی سرور.

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
VITE_SITE_URL=https://ev98.ir
```

```bash
chmod 600 /opt/ev98/.env.production
cp /opt/ev98/.env.production /opt/ev98/.env   # compose بعضی متغیرها را از .env هم می‌خواند
```

کاتالوگ خودرو از `outputs/emapna_ev_dataset/emapna_ev_normalized.csv` خوانده می‌شود و در compose به `/outputs` داخل کانتینر mount شده است.

### ۳) بالا آوردن API و DB

```bash
cd /opt/ev98
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps
curl -s http://127.0.0.1:8098/health   # باید {"status":"ok"} باشد
```

Migration با استارت api (`alembic upgrade head`) اجرا می‌شود.

### ۴) بیلد فرانت

```bash
cd /opt/ev98/frontend
npm ci
VITE_SITE_URL=https://ev98.ir npm run build
rm -rf /var/www/ev98/*
cp -a dist/. /var/www/ev98/
```

فرانت با path نسبی (`/v1/...`) به API می‌زند؛ nginx همان origin را پروکسی می‌کند.

### ۵) nginx

```bash
cp /opt/ev98/deploy/nginx-ev98.ir.conf /etc/nginx/sites-available/ev98.ir
# در صورت نیاز server_name را شامل www کنید:
#   server_name ev98.ir www.ev98.ir;
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
# 1) کد را به /opt/ev98 برسانید (rsync یا git pull)
cd /opt/ev98

# 2) API
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# 3) فرانت
cd frontend && npm ci && VITE_SITE_URL=https://ev98.ir npm run build
rm -rf /var/www/ev98/* && cp -a dist/. /var/www/ev98/

# 4) اگر nginx عوض شده
nginx -t && systemctl reload nginx
```

Volume دیتابیس (`ev98_pg`) با rebuild پاک نمی‌شود.

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
