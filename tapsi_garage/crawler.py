"""کراول کامل محصولات یک شهر (با صفحه‌بندی و مکث مؤدبانه)."""

from __future__ import annotations

import time
from typing import Callable

from . import config
from .client import TapsiGarageClient, TapsiGarageError
from .storage import ProductStore


def crawl_products(
    client: TapsiGarageClient,
    store: ProductStore,
    city_id: int = 1,
    city_title: str = "",
    category_id: int | None = None,
    subcategory_ids: list[int] | None = None,
    pages: int | None = None,          # None = همهٔ صفحات
    page_size: int = config.PAGE_SIZE_DEFAULT,
    extra_filters: dict | None = None,
    on_page: Callable[[int, int, int, int], None] | None = None,
    save_every: int = 5,
) -> dict:
    """کرال محصولات و ذخیره در دیتابیس.

    برمی‌گرداند: {"pages": n, "total": m, "products": k, "new": j}
    on_page(page_number, fetched_this_page, total_products, new_so_far)
    """
    run_id = store.start_run(city_id, city_title, category_id,
                             subcategory_ids, page_size)
    total_products = 0
    new_products = 0
    save_errors = 0
    first_save_error = ""
    page = 1
    last_page = 1
    empty_retries = 0
    MAX_EMPTY_RETRIES = 3   # تلاش مجدد برای صفحه‌های خالیِ غیرمنتظره (خزش موقت سرور)
    try:
        while True:
            result = client.get_products(
                city_id=city_id, page=page, skip=page_size,
                category_id=category_id, subcategory_ids=subcategory_ids,
                extra_filters=extra_filters,
            )
            products = result["products"]
            pagination = result["pagination"] or {}
            last_page = int(pagination.get("lastPage") or 1)
            total = int(pagination.get("total") or 0)

            # مقاوم‌سازی: صفحهٔ اولِ خالی در حالی که total > 0 است،
            # معمولاً خطای گذرا (محدودسازی لحظه‌ای) است → چند بار تلاش مجدد
            if not products and page == 1 and total > 0:
                empty_retries += 1
                if empty_retries <= MAX_EMPTY_RETRIES:
                    time.sleep(config.RETRY_BACKOFF ** empty_retries)
                    continue
                raise TapsiGarageError(
                    f"صفحهٔ اول خالی برگشت با اینکه total={total} است —"
                    " احتمالاً محدودیت موقت سرور؛ بعداً دوباره تلاش کنید."
                )

            for p in products:
                try:
                    if store.upsert_product(p):
                        new_products += 1
                    total_products += 1
                except Exception as exc:
                    # محصول معیوب نباید کل کرال را متوقف کند، اما
                    # خطای ذخیره‌سازی نباید بی‌صدا بماند (درس امروز!)
                    save_errors += 1
                    if save_errors == 1:
                        first_save_error = f"{type(exc).__name__}: {exc}"
                    continue

            if page % save_every == 0:
                store.commit()
            if on_page:
                on_page(page, len(products), total, new_products)

            # شرط پایان: همهٔ صفحات یا محدودیت کاربر یا صفحهٔ خالی (پایان طبیعی)
            if (pages is not None and page >= pages) or page >= last_page or not products:
                break
            page += 1
            time.sleep(config.CRAWL_DELAY)

        store.commit()
        store.finish_run(run_id, page, total_products, new_products,
                         "done" if not save_errors else
                         f"done ({save_errors} save errors)")
        if save_errors:
            import logging
            logging.getLogger("daemon").error(
                "⚠ %d محصول ذخیره نشد! اولین خطا: %s", save_errors, first_save_error)
        return {"pages": page, "total": total_products, "new": new_products,
                "save_errors": save_errors,
                "first_save_error": first_save_error}
    except (TapsiGarageError, KeyboardInterrupt) as exc:
        store.commit()
        store.finish_run(run_id, page, total_products, new_products,
                         f"aborted: {exc}"[:200])
        raise
