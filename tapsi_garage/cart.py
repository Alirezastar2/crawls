"""عملیات سبد خرید (Basket) تپسی گاراژ با منطق «افزودن هوشمند».

جریان افزودن به سبد در سایت به این شکل است:
  1) جزئیات محصول → گرفتن categoryId
  2) انتخاب نوع سرویس (delivery/service/shipment) و پیداکردن فروشنده
  3) گرفتن روز/شیفت کاری فروشنده (serviceDate + shiftNo)
  4) POST به add-items

کلاس Cart همهٔ این مراحل را خودکار انجام می‌دهد.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import config
from .client import TapsiGarageClient, TapsiGarageError

# پیام‌های شناخته‌شدهٔ سرور (برای نمایش دوستانه‌تر)
MSG_ALREADY_ADDED = "محصول از قبل به سبد اضافه شده است"


@dataclass
class AddResult:
    """نتیجهٔ افزودن محصول به سبد."""
    ok: bool
    product_id: str
    service_type: str | None = None
    vendor_id: str | None = None
    vendor_title: str | None = None
    service_date: str | None = None
    shift_no: int | None = None
    message: str = ""
    recommend_vendor_id: str | None = None   # سرور فروشندهٔ پیشنهادی برگرداند
    raw: Any = field(default=None)


class Cart:
    """سبد خرید تپسی گاراژ برای یک کلاینت (مهمان یا لاگین‌شده)."""

    def __init__(self, client: TapsiGarageClient):
        self.client = client

    # ─── نمایش و شمارش ───────────────────────────────────────────
    def get(self, city_id: int = 1) -> dict:
        """سبد فعلی شامل اقلام، قیمت کل و تخفیف‌ها."""
        return self.client.get_basket(city_id)

    def counts(self) -> int:
        """تعداد کل اقلام سبد."""
        return int(self.client.get_basket_counts().get("count") or 0)

    @staticmethod
    def summarize(basket: dict) -> str:
        """خلاصهٔ فارسی و خوانای سبد."""
        props = basket.get("props", basket)
        lines = []
        total = props.get("totalPrice") or 0
        without_disc = props.get("totalPriceWithoutDiscount") or 0
        discount = props.get("totalDiscount") or 0
        lines.append(f"قیمت کل: {total:,} تومان")
        if discount:
            lines.append(f"تخفیف: {discount:,} تومان "
                         f"(بدون تخفیف: {without_disc:,} تومان)")
        items = props.get("basketItems") or []
        lines.append(f"تعداد فروشنده‌ها: {len(items)}")
        for vendor in items:
            v = vendor.get("props", vendor)
            for it in v.get("items", []):
                p = it.get("props", it)
                lines.append(
                    f"  • [{p.get('quantity')}×] {p.get('productTitle')} — "
                    f"{(p.get('productPrice') or 0) * (p.get('quantity') or 1):,} تومان "
                    f"(سرویس: {p.get('serviceType')}، شیفت {p.get('shift', {}).get('no')})"
                )
        return "\n".join(lines)

    # ─── افزودن ─────────────────────────────────────────────────
    def add(self, product_id: str, city_id: int = 1, quantity: int = 1,
            service_type: str | None = None, vendor_id: str | None = None,
            service_date: str | None = None, shift_no: int | None = None,
            auto_pick_shift: bool = True) -> AddResult:
        """افزودن محصول به سبد — با رزولوشن خودکار فروشنده/روز/شیفت.

        پارامترها:
            product_id   : شناسهٔ UUID محصول
            city_id     : شهر (پیش‌فرض 1 = تهران)
            quantity    : تعداد
            service_type: "delivery" | "service" | "shipment" (None = خودکار)
            vendor_id   : فروشندهٔ مشخص (None = اولین فروشندهٔ موجود)
            service_date/shift_no : تاریخ و شیفت مشخص (None = خودکار)
        """
        # 1) جزئیات محصول → categoryId
        detail = self.client.get_product_detail(product_id, city_id)
        category_id = detail.get("categoryId")
        if not category_id:
            raise TapsiGarageError(
                "شناسهٔ دسته‌بندی محصول در جزئیات یافت نشد — محصول در این شهر "
                "موجود نیست؟", raw=detail,
            )

        # 2) نوع سرویس و فروشنده
        candidates = [service_type] if service_type else config.SERVICE_PRIORITY
        vendor: dict | None = None
        used_service: str | None = None
        for st in candidates:
            vendors = self.client.get_product_vendors(
                product_id, city_id, category_id, service_type=st, quantity=quantity,
            )
            if not vendors:
                continue
            if vendor_id:
                vendor = next((v for v in vendors if v.get("id") == vendor_id), None)
            vendor = vendor or vendors[0]
            used_service = st
            break

        if vendor is None:
            return AddResult(
                ok=False, product_id=product_id, service_type=service_type,
                message=(
                    "هیچ فروشنده‌ای برای این محصول (با سرویس‌های delivery/service) "
                    "در این شهر پیدا نشد. اگر محصول فقط «ارسال پستی» (shipment) "
                    "دارد، ثبت آدرس و معمولاً لاگین لازم است."
                ),
            )

        # 3) روز و شیفت
        if not service_date or shift_no is None:
            date, shift = self._pick_shift(
                vendor["id"], category_id, used_service, prefer_date=vendor.get("date"),
            )
            service_date = service_date or date
            shift_no = shift_no if shift_no is not None else shift

        # 4) افزودن — اگر تاریخ/شیفت منقضی شده بود، روزهای بعدی را امتحان کن
        invalid_date_msgs = ("نا معتبر", "معتبر نمی", "تاریخ خدمت", "Invalid")
        shift_candidates = [shift_no] if shift_no is not None else [4, 3, 2, 1]
        date_candidates = [service_date] + self._future_dates(count=4)
        seen: set[tuple[str, int]] = set()

        last_error: TapsiGarageError | None = None
        for s_date in date_candidates:
            for s_no in shift_candidates:
                if (s_date, s_no) in seen or s_date is None:
                    continue
                seen.add((s_date, s_no))
                try:
                    resp = self.client.add_basket_item(
                        city_id=city_id, product_id=product_id,
                        category_id=category_id, vendor_id=vendor.get("id"),
                        quantity=quantity, service_type=used_service,
                        service_date=s_date, shift_no=s_no,
                    )
                except TapsiGarageError as exc:
                    last_error = exc
                    msg = str(exc)
                    # فقط خطاهای مربوط به تاریخ/شیفت قابل تلاش مجددند
                    if any(k in msg for k in invalid_date_msgs):
                        continue
                    return AddResult(
                        ok=False, product_id=product_id, service_type=used_service,
                        vendor_id=vendor.get("id"), vendor_title=vendor.get("title"),
                        service_date=s_date, shift_no=s_no, message=msg, raw=exc.raw,
                    )
                return AddResult(
                    ok=True, product_id=product_id, service_type=used_service,
                    vendor_id=vendor.get("id"), vendor_title=vendor.get("title"),
                    service_date=s_date, shift_no=s_no,
                    recommend_vendor_id=resp.get("vendorId"),
                    message="به سبد خرید اضافه شد ✓", raw=resp,
                )

        return AddResult(
            ok=False, product_id=product_id, service_type=used_service,
            vendor_id=vendor.get("id"), vendor_title=vendor.get("title"),
            service_date=service_date, shift_no=shift_no,
            message=str(last_error) if last_error else "افزودن ناموفق بود",
            raw=last_error.raw if last_error else None,
        )

    @staticmethod
    def _future_dates(count: int = 4) -> list[str]:
        """تاریخ‌های نیمه‌شب به‌وقت تهران برای «n روز بعد» به فرمت ISO Z.

        نیمه‌شب هر روز تهران = 20:30 UTC روز قبل (UTC+3:30، بدون DST از ۲۰۲۲).
        """
        from datetime import datetime, time, timedelta, timezone

        tehran = timezone(timedelta(hours=3, minutes=30))
        now = datetime.now(tehran)
        out = []
        for n in range(1, count + 1):
            day = (now + timedelta(days=n)).date()
            midnight = datetime.combine(day, time.min, tzinfo=tehran)
            out.append(midnight.astimezone(timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        return out

    def _pick_shift(self, vendor_id: str, category_id: int, service_type: str,
                    prefer_date: str | None = None) -> tuple[str, int]:
        """انتخاب اولین روز/شیفت با ظرفیت.

        اگر لیست شیفت‌ها خالی بود، از تاریخ پیشنهادی خود فروشنده
        (vendor.date = نزدیک‌ترین روز کاری) با شیفت ۱ استفاده می‌کنیم؛
        سرور این ترکیب را می‌پذیرد.
        """
        try:
            days = self.client.get_vendor_shifts(vendor_id, category_id, service_type)
        except TapsiGarageError:
            days = []

        # روز ترجیحی (nextServiceDayCaps فروشنده) اول امتحان شود
        ordered = list(days or [])
        if prefer_date:
            ordered.sort(key=lambda d: 0 if d.get("date") == prefer_date else 1)
        for day in ordered:
            for shift in day.get("shifts") or []:
                if shift.get("hasCapacity"):
                    return day["date"], int(shift["no"])

        # fallback 1: اولین روز/شیفت موجود (حتی بدون ظرفیت)
        for day in ordered:
            shifts = day.get("shifts") or []
            if day.get("date") and shifts:
                return day["date"], int(shifts[0].get("no") or 1)

        # fallback 2: تاریخ پیشنهادی خود فروشنده + شیفت ۱
        if prefer_date:
            return prefer_date, 1

        raise TapsiGarageError(
            "هیچ روز/شیفت کاری برای این فروشنده پیدا نشد."
        )

    # ─── تغییر تعداد / حذف / خالی‌کردن ──────────────────────────
    def set_quantity(self, product_id: str, quantity: int) -> Any:
        """تغییر تعداد یک محصول در سبد (0 = حذف منطقی)."""
        return self.client.update_basket_item(product_id, quantity)

    def remove_vendor(self, vendor_id: str, is_shipment: bool = False) -> Any:
        """حذف همهٔ اقلام یک فروشنده از سبد."""
        return self.client.remove_vendor_items(vendor_id, is_shipment)

    def clear(self, city_id: int = 1) -> Any:
        """خالی‌کردن کل سبد."""
        return self.client.clear_baskets(city_id)
