"""مثال کاربردی: کرال چند صفحه محصول + افزودن به سبد خرید.

اجرا از ریشهٔ پروژه:
    python examples/basic_usage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# اجرای مستقیم فایل از پوشهٔ examples → ریشهٔ پروژه به sys.path اضافه شود
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tapsi_garage import TapsiGarageClient, Cart  # noqa: E402
from tapsi_garage.crawler import crawl_products   # noqa: E402
from tapsi_garage.storage import ProductStore     # noqa: E402


def main() -> None:
    client = TapsiGarageClient(session_file="data/session.json")
    print("guest:", client.guest_id)

    # 1) لیست شهرها
    cities = client.get_cities()
    print("شهرها:", ", ".join(f"{c['id']}={c['title']}" for c in cities))

    # 2) کرال ۲ صفحه از تهران (۸۰ محصول) — برای کلِ تهران pages=None بگذارید
    store = ProductStore("data/products.db")
    result = crawl_products(client, store, city_id=1, city_title="تهران",
                            pages=2, on_page=lambda p, n, t, nw: print(f"صفحه {p}: {n} محصول"))
    print("نتیجهٔ کرال:", result)
    store.close()

    # 3) لیست محصولات دستهٔ «لوازم یدکی» (categoryId=7)
    page = client.get_products(1, page=1, skip=5, category_id=7)
    for p in page["products"]:
        print(f"  [{p['id']}] {p['title']} — {p['price']:,} تومان"
              f" | تصویر: {p['_imageUrl']}")

    # 4) افزودن اولین محصول به سبد خرید (مهمان)
    if page["products"]:
        target = page["products"][0]
        print("\nافزودن به سبد:", target["title"])
        cart = Cart(client)
        add_result = cart.add(target["id"], city_id=1, quantity=1)
        print("نتیجه:", add_result.message or add_result.raw)

        # 5) نمایش سبد
        basket = cart.get(1)
        print("\n─ سبد خرید ─")
        print(Cart.summarize(basket))
        print("تعداد اقلام:", cart.counts())


if __name__ == "__main__":
    main()
