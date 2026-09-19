"""رابط خط فرمان (CLI) پروژهٔ کرال تپسی گاراژ.

مثال‌ها:
    python main.py cities
    python main.py categories --city 1
    python main.py subcategories --city 1 --category 1
    python main.py crawl --city 1                        # کل تهران (~3900 محصول)
    python main.py crawl --city 1 --category 7           # فقط لوازم یدکی
    python main.py crawl --city 1 --pages 3              # فقط ۳ صفحه اول
    python main.py crawl --city 1 --csv data/products.csv  # با خروجی CSV
    python main.py search "لنت ترمز"
    python main.py export --csv data/products.csv --json data/products.json
    python main.py product 81cc7ada-125d-4678-a579-0c1cbfe9626e
    python main.py vendors 81cc7ada-125d-4678-a579-0c1cbfe9626e --service delivery
    python main.py shifts a12a57c0-4506-4186-98fa-70c1552a268b 7
    python main.py cart show --city 1
    python main.py cart add 81cc7ada-125d-4678-a579-0c1cbfe9626e --qty 2
    python main.py cart qty 81cc7ada-125d-4678-a579-0c1cbfe9626e 3
    python main.py cart remove-vendor a12a57c0-4506-4186-98fa-70c1552a268b
    python main.py cart clear --city 1
    python main.py cart report          # چقدر به سبدِ سرور اضافه شده + لاگ
    python main.py cart history         # تاریخچهٔ افزودن‌ها
    python main.py changes              # تغییرات قیمت (نیاز به چند دوره کرال)
    python main.py daemon --city 1 --interval 3600 --csv data/products.csv
    python main.py guest
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# خروجی UTF-8 روی ویندوز (کنسول پیش‌فرض cp1252 است و متن فارسی را نمی‌پذیرد)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from tapsi_garage import config
from tapsi_garage.cart import Cart
from tapsi_garage.client import TapsiGarageClient, TapsiGarageError
from tapsi_garage.crawler import crawl_products
from tapsi_garage.storage import ProductStore

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "products.db"
SESSION_PATH = DATA_DIR / "session.json"


def _print(data, pretty: bool = True) -> None:
    if isinstance(data, str):
        print(data)
        return
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False))


# ─── دستورات داده ──────────────────────────────────────────────
def cmd_cities(args) -> None:
    client = TapsiGarageClient()
    cities = client.get_cities()
    _print(cities)


def cmd_categories(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    cats = client.get_categories(args.city)
    _print(cats)


def cmd_subcategories(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    subs = client.get_subcategories(args.city, args.category)
    _print(subs)


def cmd_crawl(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    store = ProductStore(DB_PATH)

    city_title = ""
    try:
        cities = {c["id"]: c.get("title", "") for c in client.get_cities()}
        city_title = cities.get(args.city, "")
    except TapsiGarageError:
        pass
    if not city_title:
        city_title = str(args.city)

    print(f"شروع کرال — شهر: {city_title} (id={args.city})"
          + (f"، دسته: {args.category}" if args.category else "")
          + (f"، زیردسته‌ها: {args.subcategories}" if args.subcategories else ""))

    def on_page(page, fetched, total, new):
        print(f"  صفحه {page}: {fetched} محصول در این صفحه "
              f"(جمع: {total}، جدید: {new})")

    try:
        result = crawl_products(
            client, store,
            city_id=args.city, city_title=city_title,
            category_id=args.category,
            subcategory_ids=args.subcategories,
            pages=args.pages, page_size=args.page_size,
            on_page=on_page,
        )
        print(f"تمام شد ✓ — {result['pages']} صفحه، "
              f"{result['total']} محصول ({result['new']} محصول جدید)")
    finally:
        stats = store.stats()
        print(f"دیتابیس: {stats['total']} محصول در {DB_PATH}")
        if args.json:
            out = store.export_json(args.json)
            print(f"خروجی JSON: {out}")
        if args.csv:
            out = store.export_csv(args.csv, delimiter=args.csv_delimiter)
            print(f"خروجی CSV: {out}")
        store.close()


def cmd_search(args) -> None:
    store = ProductStore(DB_PATH)
    if not DB_PATH.exists():
        print("اول یک کرال انجام بده: python main.py crawl --city 1")
        return
    rows = store.search(args.query)
    if not rows:
        print("چیزی پیدا نشد.")
        return
    for r in rows:
        price = f"{r['price']:,}" if r["price"] else "؟"
        print(f"[{r['id']}] {r['title']} — {price} تومان "
              f"({r['category_title'] or 'بدون دسته'})"
              + ("" if r["is_active"] else " (غیرفعال)"))


def cmd_stats(args) -> None:
    if not DB_PATH.exists():
        print("دیتابیس موجود نیست — اول کرال کن.")
        return
    store = ProductStore(DB_PATH)
    _print(store.stats())


def cmd_export(args) -> None:
    """تبدیل دیتابیس موجود به CSV/JSON (بدون کرال مجدد)."""
    if not DB_PATH.exists():
        print("دیتابیس موجود نیست — اول کرال کن: python main.py crawl --city 1")
        sys.exit(1)
    store = ProductStore(DB_PATH)
    try:
        stats = store.stats()
        print(f"{stats['total']} محصول در دیتابیس.")
        if args.csv:
            out = store.export_csv(args.csv, delimiter=args.csv_delimiter)
            print(f"✓ خروجی CSV: {out}")
        if args.json:
            out = store.export_json(args.json)
            print(f"✓ خروجی JSON: {out}")
        if not args.csv and not args.json:
            print("مسیر خروجی بده: --csv data/products.csv و/یا --json data/products.json")
    finally:
        store.close()


def cmd_product(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    detail = client.get_product_detail(args.product_id, args.city)
    # افزودن URL تصاویر و صفحهٔ محصول برای راحتی
    images = detail.get("images") or []
    for img in images:
        img["url"] = config.image_url(img.get("fileName"))
    _print(detail)


def cmd_vendors(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    detail = client.get_product_detail(args.product_id, args.city)
    cat_id = detail.get("categoryId")
    if not cat_id:
        print("محصول در این شهر یافت نشد.", file=sys.stderr)
        sys.exit(1)
    vendors = client.get_product_vendors(
        args.product_id, args.city, cat_id,
        service_type=args.service, quantity=args.quantity,
    )
    for v in vendors:
        print(f"[{v['id']}] {v.get('title')} — تاریخ: {v.get('date')}, "
              f"امتیاز: {v.get('vendorRating')}, "
              f"حداکثر ظرفیت: {v.get('maximumOrder')}")
    if not vendors:
        print(f"فروشنده‌ای با سرویس «{args.service}» پیدا نشد.")


def cmd_shifts(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    days = client.get_vendor_shifts(args.vendor_id, args.category_id, args.service)
    if not days:
        print("سرور لیست شیفت‌ها را خالی برگرداند (گاهی پیش می‌آید).")
        print("نکته: در «cart add» به‌صورت خودکار از تاریخ پیشنهادی فروشنده استفاده می‌شود.")
        return
    for day in days:
        shifts = ", ".join(
            f"شیفت{s.get('no')} ({s.get('from')}-{s.get('to')})"
            f"{'✓' if s.get('hasCapacity') else '✗'}"
            for s in day.get("shifts", [])
        )
        print(f"{day.get('date')}: {shifts}")


# ─── دستورات سبد خرید ─────────────────────────────────────────
def make_cart(args) -> tuple[TapsiGarageClient, Cart]:
    client = TapsiGarageClient(guest_id=args.guest, session_file=SESSION_PATH)
    return client, Cart(client)


def cmd_cart_show(args) -> None:
    client, cart = make_cart(args)
    basket = cart.get(args.city)
    print(f"guest: {client.guest_id}")
    print(cart.summarize(basket))


def cmd_cart_add(args) -> None:
    client, cart = make_cart(args)
    print(f"guest: {client.guest_id}")
    result = cart.add(
        args.product_id, city_id=args.city, quantity=args.qty,
        service_type=args.service, vendor_id=args.vendor,
        service_date=args.date, shift_no=args.shift,
    )
    # ثبت تلاش در لاگ محلی (برای گزارش «چقدر به سبد اضافه شد»)
    store = ProductStore(DB_PATH)
    try:
        title = ""
        try:
            title = (client.get_product_detail(args.product_id, args.city)
                     .get("title") or "")
        except Exception:
            pass
        store.log_add(
            guest_id=client.guest_id, city_id=args.city,
            product_id=args.product_id, product_title=title,
            quantity=args.qty, service_type=result.service_type,
            vendor_id=result.vendor_id, service_date=result.service_date,
            shift_no=result.shift_no, ok=result.ok, message=result.message,
        )
    finally:
        store.close()

    if result.ok:
        print(f"✓ {result.message}")
        print(f"  سرویس: {result.service_type} | فروشنده: {result.vendor_title}"
              f" ({result.vendor_id})")
        print(f"  تاریخ: {result.service_date} | شیفت: {result.shift_no}")
        if result.recommend_vendor_id and \
           result.recommend_vendor_id != result.vendor_id:
            print(f"  (سرور فروشندهٔ دیگری هم پیشنهاد داد: "
                  f"{result.recommend_vendor_id})")
    else:
        print(f"✗ {result.message}")
        sys.exit(1)
    basket = cart.get(args.city)
    print("\n─ وضعیت سبد ─")
    print(cart.summarize(basket))


def cmd_cart_qty(args) -> None:
    client, cart = make_cart(args)
    try:
        cart.set_quantity(args.product_id, args.qty)
        print("✓ تعداد به‌روزرسانی شد.")
    except TapsiGarageError as exc:
        print(f"✗ {exc}")
        sys.exit(1)


def cmd_cart_remove(args) -> None:
    client, cart = make_cart(args)
    try:
        cart.remove_vendor(args.vendor_id, args.is_shipment)
        print("✓ اقلام فروشنده حذف شد.")
    except TapsiGarageError as exc:
        print(f"✗ {exc}")
        sys.exit(1)


def cmd_cart_clear(args) -> None:
    client, cart = make_cart(args)
    try:
        cart.clear(args.city)
        print("✓ سبد خالی شد.")
    except TapsiGarageError as exc:
        print(f"✗ {exc}")
        sys.exit(1)


def cmd_cart_counts(args) -> None:
    client, cart = make_cart(args)
    print(f"guest: {client.guest_id}")
    print(f"تعداد اقلام سبد: {cart.counts()}")


def cmd_cart_report(args) -> None:
    """گزارش کامل: چقدر از طرف ما به سبدِ سرور اضافه شد + وضعیت زندهٔ سبد.

    ⚠ نکتهٔ مهم سرور: سبد مهمان به «آخرین شهری که سبدش درخواست شده» گره خورده؛
    اگر سبد شهر دیگری را GET کنید، سرور سبد فعلی را خالی می‌کند (تست‌شده).
    پس فقط سبد همان شهری که با --city می‌دهید خوانده می‌شود.
    """
    client, cart = make_cart(args)
    print(f"guest: {client.guest_id}")
    global_count = cart.counts()
    print(f"شمارش کل روی سرور: {global_count}")

    # ── وضعیت زندهٔ سبد همین شهر ──
    basket = client.get_basket(args.city)
    props = basket.get("props", basket) or {}
    items = props.get("basketItems") or []
    total_items = 0
    city_total = props.get("totalPrice") or 0
    city_discount = props.get("totalDiscount") or 0
    if items:
        print(f"\n─ سبد شهر {args.city} ─ مجموع: {city_total:,} تومان"
              + (f" | تخفیف: {city_discount:,}" if city_discount else ""))
        for vendor in items:
            v = vendor.get("props", vendor)
            for it in v.get("items", []):
                p = it.get("props", it)
                qty = p.get("quantity") or 1
                unit = p.get("productPrice") or 0
                total_items += qty
                print(f"  • [{qty}×] {p.get('productTitle')} — "
                      f"{unit * qty:,} تومان "
                      f"(سرویس: {p.get('serviceType')})")
    else:
        print(f"سبد شهر {args.city} خالی است.")
    if global_count and not items:
        print("⚠ شمارش سرور غیرصفر است ولی این شهر خالی — اقلام در سبدِ"
              " شهر دیگری‌اند؛ توجه: گرفتن سبد آن شهر، این سبد را پاک می‌کند!")

    # ── خلاصهٔ تلاش‌های محلی ──
    if DB_PATH.exists():
        store = ProductStore(DB_PATH)
        try:
            s = store.add_summary()
            print(f"\n─ لاگ محلی افزودن‌ها ─")
            print(f"کل تلاش‌ها: {s['total_attempts']} | "
                  f"موفق: {s['successful']} | ناموفق: {s['failed']}")
            for row in s["last"][:args.last]:
                mark = "✓" if row["ok"] else "✗"
                print(f"  {mark} [{row['ts'][:19]}] "
                      f"{row.get('product_title') or '?'} "
                      f"(×{row.get('quantity') or 1}) — {row.get('message') or ''}")
        finally:
            store.close()


def cmd_cart_history(args) -> None:
    """تاریخچهٔ کامل تلاش‌های افزودن به سبد."""
    if not DB_PATH.exists():
        print("لاگی موجود نیست — اول یک cart add بزن.")
        return
    store = ProductStore(DB_PATH)
    try:
        rows = store.add_history(args.limit)
        if not rows:
            print("لاگی نیست.")
            return
        for r in rows:
            mark = "✓" if r["ok"] else "✗"
            print(f"{mark} [{r['ts'][:19]}] شهر{r['city_id']} "
                  f"{r.get('product_title') or r['product_id']} "
                  f"(×{r.get('quantity') or 1}, {r.get('service_type') or '-'}) "
                  f"→ {r.get('message') or ''}")
    finally:
        store.close()


def cmd_guest(args) -> None:
    client = TapsiGarageClient(session_file=SESSION_PATH)
    if args.new:
        gid = client.new_guest()
        print(f"guest جدید ساخته شد: {gid}")
    else:
        print(f"guest فعلی: {client.guest_id}")
        print(f"فایل جلسه: {SESSION_PATH.resolve()}")


def cmd_changes(args) -> None:
    """آخرین تغییرات قیمت ثبت‌شده (نتیجهٔ کرال‌های دوره‌ای)."""
    if not DB_PATH.exists():
        print("دیتابیس موجود نیست — اول کرال کن.")
        return
    store = ProductStore(DB_PATH)
    try:
        rows = store.recent_price_changes(args.limit)
        if not rows:
            print("هنوز تغییری ثبت نشده — تغییر قیمت‌ها وقتی ثبت می‌شوند که"
                  " محصولی در کرال بعدی قیمت متفاوتی داشته باشد.")
            return
        for r in rows:
            diff = (r["new_price"] or 0) - (r["old_price"] or 0)
            arrow = "▲" if diff > 0 else "▼"
            pct = (abs(diff) / r["old_price"] * 100) if r["old_price"] else 0
            print(f"[{r['ts'][:19]}] {r.get('product_title') or r['product_id']}: "
                  f"{r['old_price']:,} → {r['new_price']:,} تومان "
                  f"({arrow} {abs(diff):,} | {pct:.1f}%)")
    finally:
        store.close()


def cmd_daemon(args) -> None:
    """حالت ۲۴/۷ برای سرور: کرال دوره‌ای + خروجی CSV/JSON + ثبت تغییر قیمت.

    هر دوره: کرال شهر → ذخیره در SQLite → خروجی CSV/JSON → مکث interval ثانیه.
    تغییر قیمت محصولات (نسبت به دورهٔ قبل) در جدول price_history ثبت می‌شود
    و با دستور «changes» قابل مشاهده است.
    """
    import logging
    from datetime import datetime as _dt

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(DATA_DIR / "daemon.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger("daemon")

    client = TapsiGarageClient(session_file=SESSION_PATH)
    store = ProductStore(DB_PATH)
    city_title = str(args.city)
    try:
        city_title = next(
            (c["title"] for c in client.get_cities() if c["id"] == args.city),
            str(args.city),
        )
    except TapsiGarageError:
        pass

    cycle = 0
    log.info("شروع دیمن — شهر %s (id=%s)، هر %s ثانیه، صفحه‌حجم %s",
             city_title, args.city, args.interval, args.page_size)
    try:
        while True:
            cycle += 1
            started = _dt.now()
            log.info("دورهٔ %d شروع شد", cycle)
            try:
                result = crawl_products(
                    client, store,
                    city_id=args.city, city_title=city_title,
                    category_id=args.category,
                    subcategory_ids=args.subcategories,
                    pages=args.pages, page_size=args.page_size,
                )
                log.info("دورهٔ %d: %d محصول (%d جدید) در %d صفحه — %.1f ثانیه",
                         cycle, result["total"], result["new"], result["pages"],
                         (_dt.now() - started).total_seconds())
                if args.csv:
                    store.export_csv(args.csv, delimiter=args.csv_delimiter)
                if args.json:
                    store.export_json(args.json)
                if args.check_cart:
                    try:
                        print(f"تعداد اقلام سبد سرور: {Cart(client).counts()}")
                    except TapsiGarageError as exc:
                        log.warning("بررسی سبد ناموفق: %s", exc)
            except TapsiGarageError as exc:
                log.error("دورهٔ %d با خطای API متوقف شد: %s (ادامه در دورهٔ بعد)",
                          cycle, exc)
            except KeyboardInterrupt:
                raise
            if args.once:
                log.info("حالت --once: پایان پس از یک دوره.")
                break
            elapsed = (_dt.now() - started).total_seconds()
            sleep_for = max(0, args.interval - elapsed)
            log.info("خواب %d ثانیه تا دورهٔ بعد...", int(sleep_for))
            try:
                time.sleep(sleep_for)
            except KeyboardInterrupt:
                raise
    except KeyboardInterrupt:
        log.info("دیمن با Ctrl+C متوقف شد (دورهٔ %d).", cycle)
    finally:
        store.close()


# ─── پارسر ─────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tapsi-garage",
        description="کرالر و کلاینت سبد خرید سایت تپسی گاراژ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cities", help="لیست شهر‌های فعال")
    p.set_defaults(func=cmd_cities)

    p = sub.add_parser("categories", help="دسته‌بندی‌های اصلی")
    p.add_argument("--city", type=int, default=1)
    p.set_defaults(func=cmd_categories)

    p = sub.add_parser("subcategories", help="زیردسته‌های دارای محصول")
    p.add_argument("--city", type=int, default=1)
    p.add_argument("--category", type=int, default=None)
    p.set_defaults(func=cmd_subcategories)

    p = sub.add_parser("crawl", help="کرال محصولات و ذخیره در دیتابیس")
    p.add_argument("--city", type=int, default=1, help="شناسهٔ شهر (پیش‌فرض ۱=تهران)")
    p.add_argument("--category", type=int, default=None, help="فقط یک دسته")
    p.add_argument("--subcategories", type=int, nargs="*", default=None,
                   help="فقط این زیردسته‌ها")
    p.add_argument("--pages", type=int, default=None, help="حداکثر صفحات (پیش‌فرض: همه)")
    p.add_argument("--page-size", type=int, default=config.PAGE_SIZE_DEFAULT)
    p.add_argument("--json", type=Path, default=None,
                   help="مسیر خروجی JSON (مثلاً data/products.json)")
    p.add_argument("--csv", type=Path, default=None,
                   help="مسیر خروجی CSV (مثلاً data/products.csv)")
    p.add_argument("--csv-delimiter", default=",",
                   help="جداکنندهٔ CSV (پیش‌فرض «,» — برای اکسل فارسی/اروپا «;»)")
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("search", help="جستجو در محصولات ذخیره‌شده")
    p.add_argument("query")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("stats", help="آمار دیتابیس")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("export", help="تبدیل دیتابیس موجود به CSV/JSON")
    p.add_argument("--csv", type=Path, default=None,
                   help="مسیر خروجی CSV (مثلاً data/products.csv)")
    p.add_argument("--csv-delimiter", default=",",
                   help="جداکنندهٔ CSV (پیش‌فرض «,»)")
    p.add_argument("--json", type=Path, default=None,
                   help="مسیر خروجی JSON")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("product", help="جزئیات یک محصول")
    p.add_argument("product_id")
    p.add_argument("--city", type=int, default=1)
    p.set_defaults(func=cmd_product)

    p = sub.add_parser("vendors", help="فروشنده‌های یک محصول")
    p.add_argument("product_id")
    p.add_argument("--city", type=int, default=1)
    p.add_argument("--service", default="delivery",
                   choices=["delivery", "service", "shipment"])
    p.add_argument("--quantity", type=int, default=1)
    p.set_defaults(func=cmd_vendors)

    p = sub.add_parser("shifts", help="روزها و شیفت‌های یک فروشنده")
    p.add_argument("vendor_id")
    p.add_argument("category_id", type=int)
    p.add_argument("--service", default="delivery",
                   choices=["delivery", "service", "shipment"])
    p.set_defaults(func=cmd_shifts)

    cart_parent = sub.add_parser("cart", help="عملیات سبد خرید")
    cart_sub = cart_parent.add_subparsers(dest="cart_command", required=True)

    def add_guest_option(p):
        p.add_argument("--guest", default=None,
                       help="شناسهٔ مهمان (پیش‌فرض: از data/session.json)")
        return p

    p = add_guest_option(cart_sub.add_parser("show", help="نمایش سبد"))
    p.add_argument("--city", type=int, default=1)
    p.set_defaults(func=cmd_cart_show)

    p = add_guest_option(cart_sub.add_parser("add", help="افزودن محصول به سبد"))
    p.add_argument("product_id")
    p.add_argument("--city", type=int, default=1)
    p.add_argument("--qty", type=int, default=1)
    p.add_argument("--service", default=None,
                   choices=["delivery", "service", "shipment"],
                   help="نوع سرویس (پیش‌فرض: خودکار)")
    p.add_argument("--vendor", default=None, help="شناسهٔ فروشندهٔ مشخص")
    p.add_argument("--date", default=None, help="تاریخ سرویس ISO")
    p.add_argument("--shift", type=int, default=None,
                   help="شمارهٔ شیفت ۱ تا ۴")
    p.set_defaults(func=cmd_cart_add)

    p = add_guest_option(cart_sub.add_parser("qty", help="تغییر تعداد"))
    p.add_argument("product_id")
    p.add_argument("qty", type=int)
    p.set_defaults(func=cmd_cart_qty)

    p = add_guest_option(cart_sub.add_parser("remove-vendor", help="حذف اقلام یک فروشنده"))
    p.add_argument("vendor_id")
    p.add_argument("--is-shipment", action="store_true")
    p.set_defaults(func=cmd_cart_remove)

    p = add_guest_option(cart_sub.add_parser("clear", help="خالی‌کردن سبد"))
    p.add_argument("--city", type=int, default=1)
    p.set_defaults(func=cmd_cart_clear)

    p = add_guest_option(cart_sub.add_parser("counts", help="تعداد اقلام"))
    p.set_defaults(func=cmd_cart_counts)

    p = add_guest_option(cart_sub.add_parser(
        "report", help="گزارش کامل: وضعیت زندهٔ سبد + لاگ افزودن‌ها"))
    p.add_argument("--city", type=int, default=1,
                   help="سبد کدام شهر خوانده شود (پیش‌فرض ۱=تهران)")
    p.add_argument("--last", type=int, default=10, help="چند تلاش آخر نمایش داده شود")
    p.set_defaults(func=cmd_cart_report)

    p = add_guest_option(cart_sub.add_parser("history", help="تاریخچهٔ افزودن‌ها"))
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_cart_history)

    p = sub.add_parser("changes", help="آخرین تغییرات قیمت ثبت‌شده")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_changes)

    p = sub.add_parser("daemon", help="کرال دوره‌ای ۲۴/۷ برای سرور")
    p.add_argument("--city", type=int, default=1)
    p.add_argument("--category", type=int, default=None)
    p.add_argument("--subcategories", type=int, nargs="*", default=None)
    p.add_argument("--pages", type=int, default=None)
    p.add_argument("--page-size", type=int, default=config.PAGE_SIZE_DEFAULT)
    p.add_argument("--interval", type=int, default=3600,
                   help="فاصلهٔ بین دوره‌ها به ثانیه (پیش‌فرض ۳۶۰۰ = هر ساعت)")
    p.add_argument("--once", action="store_true",
                   help="فقط یک دوره اجرا کن و خارج شو (مناسب cron/systemd-timer)")
    p.add_argument("--csv", type=Path, default=None,
                   help="بعد از هر دوره CSV بساز")
    p.add_argument("--json", type=Path, default=None,
                   help="بعد از هر دوره JSON بساز")
    p.add_argument("--csv-delimiter", default=",")
    p.add_argument("--check-cart", action="store_true",
                   help="بعد از هر دوره، شمارش سبد سرور هم چاپ شود")
    p.set_defaults(func=cmd_daemon)

    p = sub.add_parser("guest", help="نمایش/ساخت شناسهٔ مهمان")
    p.add_argument("--new", action="store_true", help="ساخت guest جدید")
    p.set_defaults(func=cmd_guest)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except TapsiGarageError as exc:
        print(f"✗ خطای API: {exc}", file=sys.stderr)
        if exc.status:
            print(f"  (HTTP {exc.status})", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nمتوقف شد.")
        sys.exit(130)


if __name__ == "__main__":
    main()
