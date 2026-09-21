"""کلاینت HTTP سطح‌پایین و متدهای دادهٔ تپسی گاراژ.

نکتهٔ مهم: سایت برای کاربران لاگین‌نکرده، سبد خرید را با هدر «guest»
(یک UUID تصادفی که در localStorage مرورگر ذخیره می‌شود) دنبال می‌کند.
این کلاینت همان رفتار را شبیه‌سازی می‌کند و UUID را در یک فایل جلسه
(session.json) نگه می‌دارد تا سبد خرید بین اجراها حفظ شود.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from . import config


class TapsiGarageError(Exception):
    """خطای عمومی API تپسی گاراژ (پیام‌های فارسی سرور را هم منتقل می‌کند)."""

    def __init__(self, message: str, *, status: int | None = None,
                 url: str | None = None, raw: Any = None):
        super().__init__(message)
        self.status = status
        self.url = url
        self.raw = raw


class TapsiGarageClient:
    """کلاینت API تپسی گاراژ — کرال محصولات + عملیات سبد خرید."""

    def __init__(self, guest_id: str | None = None,
                 session_file: str | Path | None = None,
                 timeout: int = config.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(config.DEFAULT_HEADERS)

        # ─── مدیریت شناسهٔ مهمان (guest) ───────────────────────────
        self.session_file = Path(session_file) if session_file else None
        if guest_id:
            self.guest_id = guest_id
        elif self.session_file and self.session_file.exists():
            try:
                self.guest_id = json.loads(
                    self.session_file.read_text(encoding="utf-8")
                ).get("guest_id", "")
            except Exception:
                self.guest_id = ""
        else:
            self.guest_id = ""
        if not self._is_uuid(self.guest_id):
            self.guest_id = str(uuid.uuid4())
            self._save_session()
        self.session.headers["guest"] = self.guest_id

    # ─── جلسه ────────────────────────────────────────────────────
    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    def _save_session(self) -> None:
        if self.session_file:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            self.session_file.write_text(
                json.dumps({"guest_id": self.guest_id}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def new_guest(self) -> str:
        """ساخت شناسهٔ مهمان جدید (سبد خالی تازه)."""
        self.guest_id = str(uuid.uuid4())
        self.session.headers["guest"] = self.guest_id
        self._save_session()
        return self.guest_id

    # ─── هستهٔ HTTP با retry ──────────────────────────────────────
    def request(self, method: str, url: str, *, params: dict | None = None,
                json_body: Any = None, retry_on_5xx: bool = True,
                _attempt: int = 1) -> Any:
        try:
            resp = self.session.request(
                method, url, params=params, json=json_body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            if _attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF ** _attempt)
                return self.request(method, url, params=params,
                                    json_body=json_body, _attempt=_attempt + 1)
            raise TapsiGarageError(f"خطای شبکه: {exc}") from exc

        # چند اندپوینت (مثل DELETE سبد) بدنهٔ خالی برمی‌گردانند
        if resp.status_code >= 500 and retry_on_5xx and _attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF ** _attempt)
            return self.request(method, url, params=params,
                                json_body=json_body, _attempt=_attempt + 1)

        text = (resp.text or "").strip()
        if not text:
            if resp.ok:
                return None
            raise TapsiGarageError(f"HTTP {resp.status_code} (بدون بدنه)",
                                   status=resp.status_code, url=url)

        try:
            data = resp.json()
        except ValueError:
            if resp.ok:
                return text
            raise TapsiGarageError(
                f"HTTP {resp.status_code}: پاسخ غیر JSON",
                status=resp.status_code, url=url, raw=text[:300],
            )

        # سرور خطاها را به شکل {"message": "..."} یا {"echo": "..."} برمی‌گرداند
        status_val = data.get("status") if isinstance(data, dict) else None
        is_error_status = isinstance(status_val, int) and status_val >= 400
        if not resp.ok or (
            isinstance(data, dict) and data.get("error") and is_error_status
        ):
            msg = data.get("message") if isinstance(data, dict) else None
            if not msg and isinstance(data, dict):
                err = data.get("error")
                msg = err.get("message") if isinstance(err, dict) else str(err)
            raise TapsiGarageError(
                msg or f"HTTP {resp.status_code}",
                status=resp.status_code, url=url, raw=data,
            )
        return data

    # ─── شهرها و دسته‌بندی‌ها ─────────────────────────────────────
    def get_cities(self, only_active: bool = True) -> list[dict]:
        """لیست شهرهای فعال. تهران id=1، کرج id=2 و ..."""
        return self.request(
            "GET", f"{config.API_V1}/cities",
            params={"isActive": "true"} if only_active else None,
        ) or []

    def get_categories(self, city_id: int) -> list[dict]:
        """دسته‌بندی‌های اصلی شهر (لوازم یدکی، برق خودرو، ...)."""
        return self.request(
            "GET", f"{config.API_V1}/categories", params={"cityId": city_id},
        ) or []

    def get_subcategories(self, city_id: int, category_id: int | None = None) -> list[dict]:
        """زیردسته‌های غیرخالی (دارای محصول) یک شهر/دسته."""
        params: dict[str, Any] = {"cityId": city_id, "isActive": "true"}
        if category_id is not None:
            params["categoryId"] = category_id
        return self.request(
            "GET", f"{config.API_V1}/subcategories/non-empties/", params=params,
        ) or []

    # ─── کاتالوگ محصولات ──────────────────────────────────────────
    def get_products(self, city_id: int, page: int = 1,
                     skip: int = config.PAGE_SIZE_DEFAULT,
                     category_id: int | None = None,
                     subcategory_ids: list[int] | None = None,
                     extra_filters: dict | None = None) -> dict:
        """یک صفحه از لیست محصولات.

        برمی‌گرداند: {"products": [...], "pagination": {...}}
        هر آیتم payload ممکن است چند productDetails (تنوع/واریانت) داشته باشد.
        """
        body: dict[str, Any] = {}
        if category_id is not None:
            body["categoryId"] = int(category_id)
        if subcategory_ids:
            body["subCategoryIds"] = [int(s) for s in subcategory_ids]
        if extra_filters:
            body.update(extra_filters)

        data = self.request(
            "POST", f"{config.CATALOG_BASE}/products/{int(city_id)}",
            params={"page": page, "skip": skip}, json_body=body,
        ) or {}

        # ساختار پاسخ: {payload: {cityId, productDetails: [...], pagination},
        #               pagination: {...}, status, ...}
        payload = data.get("payload") or {}
        if isinstance(payload, dict):
            raw_products = payload.get("productDetails") or []
        else:  # برای سازگاری اگر ساختار لیستی برگردد
            raw_products = []
            for group in payload:
                raw_products.extend(
                    (group.get("productDetails") if isinstance(group, dict) else [])
                    or []
                )
        products: list[dict] = []
        for pd in raw_products:
            item = dict(pd)
            item["_imageUrl"] = config.image_url(pd.get("image"))
            products.append(item)
        pagination = data.get("pagination") or (
            payload.get("pagination") if isinstance(payload, dict) else None
        ) or {}
        return {"products": products, "pagination": pagination}

    # ─── جزئیات محصول / فروشنده‌ها / شیفت‌ها ──────────────────────
    def get_product_detail(self, product_id: str, city_id: int = 1) -> dict:
        """جزئیات کامل محصول (توضیحات، تصاویر، قیمت، دسته و ...)."""
        return self.request(
            "GET", f"{config.API_V1}/products/{product_id}/cities/{int(city_id)}"
        ) or {}

    def get_product_vendors(self, product_id: str, city_id: int, category_id: int,
                            service_type: str = "delivery",
                            quantity: int = 1) -> list[dict]:
        """فروشنده‌هایی که محصول را با نوع سرویس داده‌شده ارائه می‌کنند."""
        return self.request(
            "GET",
            f"{config.API_V1}/vendors/products/{product_id}/cities/{int(city_id)}"
            f"/categories/{int(category_id)}",
            params={"serviceType": service_type, "quantity": quantity},
        ) or []

    def get_vendor_shifts(self, vendor_id: str, category_id: int,
                          service_type: str = "delivery") -> list[dict]:
        """روزها و شیفت‌های کاری یک فروشنده.

        خروجی: [{"date": "ISO", "shifts": [{"no": 4, "from": 18, "to": 20,
                                            "hasCapacity": true, ...}]}]
        """
        return self.request(
            "GET",
            f"{config.API_V1}/vendors/{vendor_id}/categories/{int(category_id)}",
            params={"serviceType": service_type},
        ) or []

    def get_product_addons(self, product_id: str, city_id: int,
                           vendor_id: str | None = None,
                           service_type: str | None = None) -> Any:
        """خدمات جانبی (add-on) محصول در یک شهر."""
        params: dict[str, Any] = {}
        if vendor_id:
            params["vendorId"] = vendor_id
        if service_type:
            params["serviceType"] = service_type
        return self.request(
            "GET",
            f"{config.CATALOG_BASE}/product/{product_id}/city/{int(city_id)}/add-ons",
            params=params or None,
        )

    # ─── سبد خرید (پیاده‌سازی در cart.py از این متدها استفاده می‌کند) ─
    def get_basket(self, city_id: int = 1) -> dict:
        """سبد فعلی مهمان/کاربر در یک شهر."""
        return self.request(
            "GET", f"{config.API_V1}/baskets/cities/{int(city_id)}"
        ) or {}

    def get_basket_counts(self) -> dict:
        """تعداد آیتم‌های سبد در همهٔ شهرها: {"count": N}"""
        return self.request("GET", f"{config.API_V1}/baskets/get-counts") or {}

    def add_basket_item(self, city_id: int, product_id: str, category_id: int,
                        vendor_id: str | None, quantity: int = 1,
                        service_type: str = "delivery",
                        service_date: str | None = None, shift_no: int = 1,
                        dynamic_service_type: str = "",
                        address_id: str | None = None) -> dict:
        """افزودن محصول به سبد — POST /baskets/cities/{cityId}/add-items.

        پاسخ موفق: {"status": 200, "vendorId": "...", "hasRecommend": false}
        """
        body = {
            "productId": product_id,
            "categoryId": int(category_id),
            "vendorId": vendor_id,
            "quantity": int(quantity),
            "serviceType": service_type,
            "serviceDate": service_date or "",
            "dynamicServiceType": dynamic_service_type,
            "shiftNo": int(shift_no),
            "addressId": address_id,
        }
        return self.request(
            "POST",
            f"{config.API_V1}/baskets/cities/{int(city_id)}/add-items",
            json_body=body,
        ) or {}

    def update_basket_item(self, product_id: str, quantity: int) -> Any:
        """تغییر تعداد یک محصول در سبد — PUT /baskets/update-items."""
        return self.request(
            "PUT", f"{config.API_V1}/baskets/update-items",
            json_body={"productId": product_id, "quantity": int(quantity)},
        )

    def remove_vendor_items(self, vendor_id: str, is_shipment: bool = False) -> Any:
        """حذف همهٔ اقلام یک فروشنده از سبد."""
        return self.request(
            "DELETE",
            f"{config.API_V1}/baskets/remove-vendor-items/vendors/{vendor_id}",
            params={"is-shipment": str(is_shipment).lower()},
        )

    def clear_baskets(self, city_id: int = 1) -> Any:
        """خالی‌کردن کل سبد شهر — DELETE /baskets/clear-baskets."""
        return self.request(
            "DELETE", f"{config.API_V1}/baskets/clear-baskets",
            json_body={"cityId": int(city_id)},
        )
