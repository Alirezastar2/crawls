# کراولر تپسی گاراژ (Tapsi Garage Crawler)

کراولر کامل سایت [تپسی گاراژ](https://tapsi-garage.ir/) به همراه **کلاینت سبد خرید** —
دریافت محصولات، جزئیات، فروشنده‌ها، شیفت‌ها و **افزودن به سبد خرید** (حتی بدون لاگین،
دقیقاً مثل خود سایت با سشن مهمان).

> ⚠️ **اخلاق کرالینگ**: این پروژه از همان API عمومی‌ای استفاده می‌کند که خود سایت
> در مرورگر شما صدا می‌زند. مکث بین درخواست‌ها (پیش‌فرض ۰.۵ ثانیه) رعایت شده تا
> به سرور فشار نیاید. از آن مسئولانه و فقط برای مصارف مشروع استفاده کنید.

---

## چطور کار می‌کند؟

سایت تپسی گاراژ یک PWA ساخته‌شده با Next.js است که در سمت مرورگر رندر می‌شود و
داده‌ها را از API های زیر می‌گیرد (با تحلیل باندل‌های JS سایت و تست زنده استخراج
و در سپتامبر ۲۰۲۶ همه تأیید شده‌اند):

| بخش | آدرس پایه |
|---|---|
| API اصلی (NestJS) | `https://tapsi-garage.ir/api/v1` |
| کاتالوگ محصولات | `https://new.tapsi-garage.ir/product-catalog/api` |
| CDN تصاویر | `https://static.tapsi-garage.ir/{fileName}` |

اندپوینت‌های کلیدی:

- `POST /product-catalog/api/products/{cityId}?page=&skip=` — لیست محصولات (با فیلتر
  `categoryId`، `subCategoryIds[]` در بدنه)
- `GET /api/v1/cities?isActive=true` — شهرها (تهران=۱، کرج=۲، …)
- `GET /api/v1/products/{productId}/cities/{cityId}` — جزئیات محصول
- `GET /api/v1/vendors/products/{productId}/cities/{cityId}/categories/{categoryId}?serviceType=` — فروشنده‌های محصول
- `GET /api/v1/vendors/{vendorId}/categories/{categoryId}?serviceType=` — روزها/شیفت‌های فروشنده
- `GET /api/v1/baskets/cities/{cityId}` — سبد خرید (با هدر `guest`)
- `POST /api/v1/baskets/cities/{cityId}/add-items` — افزودن به سبد
- `PUT /api/v1/baskets/update-items` — تغییر تعداد
- `DELETE /api/v1/baskets/remove-vendor-items/vendors/{vendorId}` — حذف اقلام یک فروشنده
- `DELETE /api/v1/baskets/clear-baskets` — خالی‌کردن سبد

**نکتهٔ مهم سبد خرید:** سایت برای کاربران مهمان، سبد را با هدر `guest` (یک UUID
که در localStorage مرورگر ذخیره می‌شود) دنبال می‌کند. این پروژه همین UUID را در
`data/session.json` نگه می‌دارد تا سبد بین اجراها حفظ شود.

جریان افزودن به سبد (که `Cart.add` خودکار انجام می‌دهد):

```
جزئیات محصول → categoryId
    ↓
انتخاب سرویس (delivery|service|shipment) + اولین فروشندهٔ موجود
    ↓
انتخاب روز/شیفت با ظرفیت از شیفت‌های فروشنده (serviceDate + shiftNo)
    ↓
POST add-items {productId, categoryId, vendorId, quantity, serviceType,
                serviceDate, dynamicServiceType, shiftNo, addressId}
```

- `delivery` = تحویل حضوری، `service` = تعویض در اتوسرویس — هر دو با تاریخ+شیفت کار می‌کنند.
- `shipment` = ارسال پستی که **آدرس ثبت‌شده (و معمولاً لاگین با OTP)** لازم دارد؛
  بدون آن سرور پیام «آدرس کاربر یافت نشد» می‌دهد.

---

## نصب

```bash
# پایتون ۳.۱۰ به بالا
pip install -r requirements.txt
```

## استفاده از خط فرمان

```bash
# شهرهای فعال
python main.py cities

# دسته‌بندی‌ها و زیردسته‌ها
python main.py categories --city 1
python main.py subcategories --city 1 --category 1

# کرال کل تهران (~۳۹۰۰ محصول، حدود ۱۰۰ صفحه) با خروجی JSON و CSV
python main.py crawl --city 1 --json data/products.json --csv data/products.csv

# فقط خروجی CSV از دیتابیس موجود (بدون کرال مجدد)
python main.py export --csv data/products.csv

# اگر اکسل ستون‌ها را در یک ستون نشان داد، از جداکنندهٔ «;» استفاده کنید:
python main.py export --csv data/products.csv --csv-delimiter ";"

# کرال فقط یک دسته (مثلاً «لوازم یدکی» با id=7)
python main.py crawl --city 1 --category 7

# کرال فقط ۳ صفحهٔ اول
python main.py crawl --city 1 --pages 3

# جستجو و آمار دیتابیس و تبدیل به CSV/JSON
python main.py search "لنت ترمز"
python main.py stats
python main.py export --csv data/products.csv --json data/products.json

# جزئیات محصول / فروشنده‌ها / شیفت‌ها
python main.py product 81cc7ada-125d-4678-a579-0c1cbfe9626e
python main.py vendors 81cc7ada-125d-4678-a579-0c1cbfe9626e --service delivery
python main.py shifts a12a57c0-4506-4186-98fa-70c1552a268b 7

# ── سبد خرید ──
python main.py guest                          # شناسهٔ مهمان فعلی
python main.py guest --new                    # سبد تازه
python main.py cart counts
python main.py cart show --city 1
python main.py cart add 81cc7ada-125d-4678-a579-0c1cbfe9626e --qty 2
python main.py cart add <id> --service service --shift 4   # با گزینه‌های دستی
python main.py cart qty <productId> 3
python main.py cart remove-vendor <vendorId>
python main.py cart clear --city 1
python main.py cart report          # چقدر به سبدِ سرور اضافه شده + لاگ محلی
python main.py cart history         # تاریخچهٔ کامل تلاش‌های افزودن
python main.py changes              # تغییرات قیمت (نتیجهٔ کرال‌های دوره‌ای)
python main.py demand --hours 24    # برآورد تقاضا: چه چیزهایی فروش رفت/برگشت

# ── کرال ۲۴/۷ روی سرور ──
python main.py daemon --city 1 --interval 3600 --csv data/products.csv --json data/products.json
python main.py daemon --city 1 --once        # یک دوره و خروج (مناسب cron)
```

### ⚠ رفتار مهم سرور: سبد مهمان تک‌شهری است!

با تست زنده ثابت شد: سبد مهمان به **آخرین شهری که سبدش درخواست شده** گره خورده و
اگر `GET /baskets/cities/{شهر دیگر}` بزنید، سرور کل سبد فعلی را **خالی می‌کند**
(مثل تغییر شهر در خود سایت). پس:

- همیشه با یک شهر کار کنید (`--city 1`).
- `cart report` فقط سبد همان شهر را می‌خواند و اگر شمارش سرور غیرصفر ولی سبد خالی
  بود، هشدار می‌دهد که اقلام در شهر دیگری‌اند.

### پیام‌های رایج سرور هنگام افزودن

| پیام | معنی |
|---|---|
| `به سبد خرید اضافه شد ✓` | موفق |
| `محصول از قبل به سبد اضافه شده است` | محصول تکراری است |
| `ظرفیت خرید این محصول به پایان رسیده` | موجودی آن شیفت تمام شده — شیفت/روز دیگری امتحان کنید |
| `تایم انتخاب شده معتبر نمی باشد` | تاریخ/شیفت نامعتبر است |
| `آدرس کاربر یافت نشد` | سرویس `shipment` است و نیاز به آدرس/لاگین دارد |
| `تاریخ خدمت نمیتواند خالی باشد` | `serviceDate` خالی ارسال شده |

## استفاده به‌عنوان کتابخانه

```python
from tapsi_garage import TapsiGarageClient, Cart
from tapsi_garage.crawler import crawl_products
from tapsi_garage.storage import ProductStore

client = TapsiGarageClient(session_file="data/session.json")

# کرال کامل تهران و ذخیره در SQLite
store = ProductStore("data/products.db")
crawl_products(client, store, city_id=1, city_title="تهران")
print(store.stats())

# افزودن محصول به سبد مهمان
cart = Cart(client)
result = cart.add("81cc7ada-125d-4678-a579-0c1cbfe9626e", city_id=1, quantity=2)
print(result.ok, result.message)

print(Cart.summarize(cart.get(1)))   # خلاصهٔ سبد با قیمت‌ها
```

## ساختار پروژه

```
tapsi-garage-crawler/
├── main.py                  # CLI کامل
├── requirements.txt         # فقط requests
├── examples/basic_usage.py  # مثال سرتاسری
├── deploy/                  # استقرار ۲۴/۷ روی سرور (systemd/cron/Docker)
│   ├── README-server.md     # راهنمای گام‌به‌گام سرور
│   ├── tapsi-garage.service # systemd service (حالت همیشه‌روشن)
│   ├── tapsi-garage.timer.service + .timer  # systemd timer (دوره‌ای)
├── tapsi_garage/
│   ├── config.py            # آدرس‌ها و تنظیمات (همهٔ اندپوینت‌ها اینجاست)
│   ├── client.py            # کلاینت HTTP + guest session + همهٔ متدهای API
│   ├── cart.py              # منطق سبد خرید (افزودن هوشمند + تلاش مجدد تاریخ/شیفت)
│   ├── crawler.py           # کرالر صفحه‌به‌صفحه با upsert و مقاوم‌سازی
│   └── storage.py           # SQLite + CSV/JSON + add_log + price_history
└── data/                    # خروجی‌ها (products.db، session.json، daemon.log، ...)
```

## گزارش «چقدر به سبد اضافه شد؟»

- هر `cart add` در جدول `add_log` ثبت می‌شود (نتیجه، پیام سرور، فروشنده، تاریخ/شیفت).
- `python main.py cart report` → وضعیت زندهٔ سبد روی سرور (اقلام + قیمت کل + تخفیف)
- `python main.py demand --hours 24` → **برآورد تقاضای بازار**: تعداد سبدهای دیگران
  خصوصی است و از هیچ API در دسترس نیست؛ نزدیک‌ترین سیگنال عمومی، رخدادهای
  «ناموش شد» (خریده شد) و «به فروش برگشت» است که دیمن خودکار ثبت می‌کند.
  + خلاصهٔ تلاش‌ها (چند موفق/ناموفق).
- `python main.py cart history` → تاریخچهٔ کامل.
- نکته: شمارش سرور جهانی است ولی هر سبد مهمان به یک شهر گره خورده (بالا توضیح دادم).

## کرال ۲۴/۷ روی سرور

دستور `daemon` هر دوره: کرال → ذخیره SQLite → ساخت CSV/JSON → مکث `--interval`
ثانیه. تغییر قیمت‌ها بین دوره‌ها در `price_history` ثبت و با `changes` دیده می‌شوند.
لاگ: `data/daemon.log`. راهنمای کامل استقرار (systemd/timer/cron/Docker) در
`deploy/README-server.md`.

## نکته‌ها و محدودیت‌ها

- **داده‌های ذخیره‌شده**: id، SKU، عنوان، دسته/زیردسته، برند، قیمت، قیمت بازار،
  تصویر، سرویس‌ها، مشخصات فنی (JSON)، محدودیت سفارش و کل JSON خام.
- کرال upsert است؛ اجرای دوباره فقط محصولات جدید را اضافه و `last_seen` را
  به‌روز می‌کند (مناسب پایش تغییر قیمت).
- پرداخت و ثبت سفارش نهایی نیاز به لاگین با شمارهٔ موبایل (OTP) دارد که در
  محدودهٔ این پروژه نیست؛ اما سبد مهمان کاملاً مثل مرورگر کار می‌کند و همین سبد
  را در سایت/اپ واقعی می‌بینید.
- اگر API در آینده تغییر کند، فقط `tapsi_garage/config.py` را به‌روز کنید.
# crawls
