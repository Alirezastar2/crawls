"""ذخیره‌سازی نتایج کرال در SQLite و خروجی JSON."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config


class ProductStore:
    """ذخیرهٔ محصولات کرال‌شده در SQLite (upsert بر اساس id)."""

    def __init__(self, db_path: str | Path = "data/products.db"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    # ─── اسکیما ──────────────────────────────────────────────────
    def _create_tables(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id            TEXT PRIMARY KEY,
                sku           TEXT,
                title         TEXT,
                category_id   INTEGER,
                category_title TEXT,
                subcategory_ids TEXT,     -- JSON array
                brand_id      INTEGER,
                price         INTEGER,
                market_price  INTEGER,
                image_file    TEXT,
                image_url     TEXT,
                is_package    INTEGER,
                is_active     INTEGER,
                is_virtual    INTEGER,
                services      TEXT,        -- JSON array
                specifications TEXT,        -- JSON
                min_order     INTEGER,
                max_order     INTEGER,
                description   TEXT,
                raw           TEXT,        -- کل JSON محصول
                first_seen    TEXT,
                last_seen     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
            CREATE INDEX IF NOT EXISTS idx_products_title ON products(title);

            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY, title TEXT, slug TEXT, raw TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY, title TEXT, raw TEXT
            );
            CREATE TABLE IF NOT EXISTS crawl_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_id INTEGER, city_title TEXT,
                category_id INTEGER, subcategory_ids TEXT,
                pages INTEGER, page_size INTEGER,
                total INTEGER, new_products INTEGER,
                started_at TEXT, finished_at TEXT, status TEXT
            );
            CREATE TABLE IF NOT EXISTS add_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, guest_id TEXT,
                city_id INTEGER, product_id TEXT, product_title TEXT,
                quantity INTEGER, service_type TEXT, vendor_id TEXT,
                service_date TEXT, shift_no INTEGER,
                ok INTEGER, message TEXT
            );
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, product_id TEXT, product_title TEXT,
                old_price INTEGER, new_price INTEGER,
                old_market_price INTEGER, new_market_price INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_price_history_ts ON price_history(ts);
            """
        )
        self.conn.commit()

    # ─── نوشتن ──────────────────────────────────────────────────
    def upsert_product(self, p: dict) -> bool:
        """درج/به‌روزرسانی یک محصول. True یعنی محصول جدید بوده.

        اگر قیمت تغییر کرده باشد در price_history ثبت می‌شود.
        """
        now = datetime.now(timezone.utc).isoformat()
        old = self.conn.execute(
            "SELECT price, market_price, title FROM products WHERE id = ?",
            (p.get("id"),),
        ).fetchone()
        new_price = p.get("price")
        new_market = p.get("marketPrice")
        if old is not None and old["price"] is not None and \
                new_price is not None and int(old["price"]) != int(new_price):
            self.conn.execute(
                "INSERT INTO price_history (ts, product_id, product_title,"
                " old_price, new_price, old_market_price, new_market_price)"
                " VALUES (?,?,?,?,?,?,?)",
                (now, p.get("id"), old["title"], int(old["price"]),
                 int(new_price), int(old["market_price"] or 0),
                 int(new_market or 0)),
            )
        self.conn.execute(
            """
            INSERT INTO products (
                id, sku, title, category_id, category_title, subcategory_ids,
                brand_id, price, market_price, image_file, image_url,
                is_package, is_active, is_virtual, services, specifications,
                min_order, max_order, description, raw, first_seen, last_seen
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                sku=excluded.sku, title=excluded.title,
                category_id=excluded.category_id,
                category_title=excluded.category_title,
                subcategory_ids=excluded.subcategory_ids,
                brand_id=excluded.brand_id, price=excluded.price,
                market_price=excluded.market_price,
                image_file=excluded.image_file, image_url=excluded.image_url,
                is_package=excluded.is_package, is_active=excluded.is_active,
                is_virtual=excluded.is_virtual, services=excluded.services,
                specifications=excluded.specifications,
                min_order=excluded.min_order, max_order=excluded.max_order,
                description=excluded.description, raw=excluded.raw,
                last_seen=excluded.last_seen
            """,
            (
                p.get("id"), p.get("SKU"), p.get("title"),
                p.get("categoryId"), p.get("categoryTitle"),
                json.dumps(p.get("subCategoryIds") or p.get("subcategories") or [],
                           ensure_ascii=False),
                p.get("brandId"), p.get("price"), p.get("marketPrice"),
                (p.get("image") if isinstance(p.get("image"), str) else None),
                p.get("_imageUrl"), int(bool(p.get("isPackage"))),
                int(bool(p.get("isActive"))), int(bool(p.get("isVirtual"))),
                json.dumps(p.get("services") or [], ensure_ascii=False),
                json.dumps(p.get("specifications") or {}, ensure_ascii=False),
                p.get("minOrder"), p.get("maxOrder"), p.get("description"),
                json.dumps(p, ensure_ascii=False),
                now, now,
            ),
        )
        return old is None

    def upsert_cities(self, cities: Iterable[dict]) -> None:
        for c in cities:
            self.conn.execute(
                "INSERT INTO cities (id, title, slug, raw) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, raw=excluded.raw",
                (c.get("id"), c.get("title"), c.get("slug"),
                 json.dumps(c, ensure_ascii=False)),
            )
        self.conn.commit()

    def upsert_categories(self, cats: Iterable[dict]) -> None:
        for c in cats:
            self.conn.execute(
                "INSERT INTO categories (id, title, raw) VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, raw=excluded.raw",
                (c.get("id"), c.get("title"), json.dumps(c, ensure_ascii=False)),
            )
        self.conn.commit()

    def start_run(self, city_id: int, city_title: str = "", category_id: int | None = None,
                  subcategory_ids: list[int] | None = None,
                  page_size: int = config.PAGE_SIZE_DEFAULT) -> int:
        cur = self.conn.execute(
            "INSERT INTO crawl_runs (city_id, city_title, category_id, subcategory_ids,"
            " pages, page_size, total, new_products, started_at, status)"
            " VALUES (?,?,?,?,0,?,0,0,?,'running')",
            (city_id, city_title, category_id,
             json.dumps(subcategory_ids or []), page_size,
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, pages: int, total: int,
                   new_products: int, status: str = "done") -> None:
        self.conn.execute(
            "UPDATE crawl_runs SET pages=?, total=?, new_products=?,"
            " finished_at=?, status=? WHERE id=?",
            (pages, total, new_products, datetime.now(timezone.utc).isoformat(),
             status, run_id),
        )
        self.conn.commit()

    def commit(self) -> None:
        self.conn.commit()

    # ─── گزارش افزودن به سبد (add_log) ───────────────────────────
    def log_add(self, guest_id: str, city_id: int, product_id: str,
                product_title: str, quantity: int, service_type: str | None,
                vendor_id: str | None, service_date: str | None,
                shift_no: int | None, ok: bool, message: str) -> None:
        self.conn.execute(
            "INSERT INTO add_log (ts, guest_id, city_id, product_id, product_title,"
            " quantity, service_type, vendor_id, service_date, shift_no, ok, message)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), guest_id, city_id,
             product_id, product_title, quantity, service_type, vendor_id,
             service_date, shift_no, int(bool(ok)), message),
        )
        self.conn.commit()

    def add_summary(self) -> dict:
        """خلاصهٔ تلاش‌های افزودن به سبد."""
        row = self.conn.execute(
            "SELECT COUNT(*) total, SUM(ok) ok_count, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) failed"
            " FROM add_log"
        ).fetchone()
        last = self.conn.execute(
            "SELECT ts, product_title, quantity, ok, message FROM add_log"
            " ORDER BY id DESC LIMIT 10"
        ).fetchall()
        return {
            "total_attempts": row["total"] or 0,
            "successful": row["ok_count"] or 0,
            "failed": row["failed"] or 0,
            "last": [dict(r) for r in last],
        }

    def add_history(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, city_id, product_id, product_title, quantity, service_type,"
            " vendor_id, service_date, shift_no, ok, message FROM add_log"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── تغییرات قیمت (price_history) ─────────────────────────────
    def recent_price_changes(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, product_id, product_title, old_price, new_price,"
            " old_market_price, new_market_price FROM price_history"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()

    # ─── خواندن ──────────────────────────────────────────────────
    def search(self, query: str, limit: int = 50) -> list[dict]:
        """جستجوی ساده در عنوان محصولات."""
        rows = self.conn.execute(
            "SELECT id, title, price, market_price, category_title, image_url,"
            " is_active FROM products WHERE title LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def all_products(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, title, price, market_price, category_title, image_url,"
            " is_active FROM products ORDER BY category_id, title"
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        total = self.conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        by_cat = self.conn.execute(
            "SELECT category_id, category_title, COUNT(*) c FROM products"
            " GROUP BY category_id ORDER BY c DESC"
        ).fetchall()
        return {"total": total,
                "by_category": [dict(r) for r in by_cat]}

    # ستون‌های خروجی (مشترک بین JSON و CSV)
    EXPORT_COLUMNS = [
        "id", "sku", "title", "category_id", "category_title", "subcategory_ids",
        "brand_id", "price", "market_price", "image_file", "image_url",
        "is_package", "is_active", "is_virtual", "services", "specifications",
        "min_order", "max_order", "description", "first_seen", "last_seen",
    ]

    def _export_rows(self) -> list[dict]:
        """خواندن همهٔ محصولات برای خروجی (فیلدهای JSON تودرتو باز می‌شوند)."""
        cols = ", ".join(self.EXPORT_COLUMNS)
        rows = self.conn.execute(f"SELECT {cols} FROM products").fetchall()
        data = []
        for r in rows:
            d = dict(r)
            for k in ("subcategory_ids", "services", "specifications"):
                try:
                    d[k] = json.loads(d[k]) if d[k] else []
                except Exception:
                    d[k] = []
            data.append(d)
        return data

    def export_json(self, out_path: str | Path) -> Path:
        """خروجی JSON همهٔ محصولات (بدون فیلد سنگین raw)."""
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = self._export_rows()
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        return out

    def export_csv(self, out_path: str | Path, delimiter: str = ",") -> Path:
        """خروجی CSV همهٔ محصولات.

        - utf-8-sig (با BOM) تا اکسل متن فارسی را درست باز کند
        - فیلدهای لیستی/تودرتو (services و ...) به رشتهٔ JSON فشرده تبدیل می‌شوند
        - delimiter می‌تواند ";" برای تنظیمات منطقه‌ای اکسل اروپا باشد
        """
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = self._export_rows()
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(self.EXPORT_COLUMNS)
            for d in data:
                row = []
                for k in self.EXPORT_COLUMNS:
                    v = d[k]
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v, ensure_ascii=False)
                    row.append(v)
                writer.writerow(row)
        return out
