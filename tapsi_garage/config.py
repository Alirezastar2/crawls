"""تنظیمات و آدرس‌های API سایت تپسی گاراژ.

این آدرس‌ها با مهندسی معکوس فرانت‌اند Next.js سایت و تست زنده استخراج
شده‌اند (سپتامبر ۲۰۲۶) و همگی سمت سرور تست شده‌اند.
"""

from __future__ import annotations

# ─── آدرس‌های پایه ────────────────────────────────────────────────
SITE_BASE = "https://tapsi-garage.ir"

# API اصلی (NestJS) — اکثر اندپوینت‌ها زیر /v1 هستند
API_BASE = "https://tapsi-garage.ir/api"
API_V1 = API_BASE + "/v1"

# API کاتالوگ محصولات (لیستینگ/فیلتر محصولات)
CATALOG_BASE = "https://new.tapsi-garage.ir/product-catalog/api"

# CDN تصاویر — fileName محصول را مستقیم به این آدرس بچسبانید
STATIC_BASE = "https://static.tapsi-garage.ir"

# ─── تنظیمات درخواست ─────────────────────────────────────────────
DEFAULT_TIMEOUT = 30          # ثانیه
MAX_RETRIES = 3               # تعداد تلاش مجدد روی خطای شبکه/5xx
RETRY_BACKOFF = 1.5           # ضریب تأخیر بین تلاش‌ها (ثانیه)
PAGE_SIZE_DEFAULT = 40        # تعداد محصول در هر صفحهٔ کاتالوگ (مثل خود سایت)
CRAWL_DELAY = 0.5             # مکث بین صفحات برای فشار نیاوردن به سرور (ثانیه)

# ترتیب اولویت سرویس‌ها برای افزودن خودکار به سبد:
#   delivery = تحویل حضوری (بدون نیاز به آدرس)
#   service  = تعویض در اتوسرویس
#   shipment = ارسال پستی (نیاز به آدرس ثبت‌شده دارد و بدون لاگین کار نمی‌کند)
SERVICE_PRIORITY = ("delivery", "service", "shipment")

# هدرهای پیش‌فرض (شبیه مرورگر)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Origin": SITE_BASE,
    "Referer": SITE_BASE + "/",
}


def image_url(file_name: str | None) -> str | None:
    """ساخت URL کامل تصویر از fileName محصول."""
    if not file_name:
        return None
    return f"{STATIC_BASE}/{file_name}"


def product_page_url(city_slug: str, category_id, category_slug: str,
                     product_id: str, product_slug: str) -> str:
    """ساخت URL صفحهٔ محصول در سایت (برای لینک‌دادن در خروجی)."""
    return (
        f"{SITE_BASE}/city/{city_slug}/category/{category_id}/{category_slug}"
        f"/product/{product_id}/{product_slug}"
    )
