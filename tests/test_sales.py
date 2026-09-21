"""Tests for per-product saleCount snapshots."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tapsi_garage.storage import ProductStore


class SaleSnapshotsTest(unittest.TestCase):
    def test_first_last_and_city_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductStore(Path(directory) / "products.db")
            try:
                store.save_sale_snapshot(1, "tyre", "Tire", 10)
                self.assertEqual(store.sale_deltas(1), [])
                store.save_sale_snapshot(1, "tyre", "Tire", 12)
                store.save_sale_snapshot(1, "tyre", "Tire", 18)
                store.save_sale_snapshot(2, "tyre", "Tire", 100)
                rows = store.sale_deltas(1)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["first_count"], 10)
                self.assertEqual(rows[0]["last_count"], 18)
                self.assertEqual(rows[0]["delta"], 8)
                self.assertEqual(rows[0]["samples"], 3)
                self.assertEqual(store.sale_deltas(2), [])
            finally:
                store.close()

    def test_reject_invalid_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductStore(Path(directory) / "products.db")
            try:
                for value in (-1, True, "10"):
                    with self.assertRaises(ValueError):
                        store.save_sale_snapshot(1, "x", "X", value)
            finally:
                store.close()

    def test_locked_csv_keeps_previous_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProductStore(root / "products.db")
            output = root / "products.csv"
            output.write_text("previous", encoding="utf-8")
            try:
                store.upsert_product({"id": "x", "title": "X", "cityId": 1})
                store.commit()
                with patch("tapsi_garage.storage.os.replace",
                           side_effect=PermissionError("locked")):
                    with self.assertRaises(PermissionError):
                        store.export_csv(output)
                self.assertEqual(output.read_text(encoding="utf-8"), "previous")
                self.assertEqual(list(root.glob(".products.csv.*.tmp")), [])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
