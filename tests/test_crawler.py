"""Regression tests for incomplete crawls and alternative API payloads."""

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from tapsi_garage.client import TapsiGarageClient, TapsiGarageError
from tapsi_garage.crawler import crawl_products
from tapsi_garage.storage import ProductStore


class FakeClient:
    def __init__(self, empty_second_page=False, crash=False, empty_catalog=False):
        self.empty_second_page = empty_second_page
        self.crash = crash
        self.empty_catalog = empty_catalog
        self.second_page_calls = 0
        self.first_page_calls = 0

    def get_products(self, city_id, page, **kwargs):
        if page == 1:
            self.first_page_calls += 1
            if self.empty_catalog:
                return {"products": [], "pagination": {"lastPage": 1, "total": 0}}
            return {"products": [{"id": "first", "title": "First", "cityId": city_id,
                                  "price": 1}],
                    "pagination": {"lastPage": 2, "total": 2}}
        self.second_page_calls += 1
        if self.crash:
            raise RuntimeError("unexpected failure")
        return {"products": [] if self.empty_second_page else
                [{"id": "second", "title": "Second", "cityId": city_id, "price": 2}],
                "pagination": {"lastPage": 2, "total": 2}}


class CrawlerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = ProductStore(Path(self.directory.name) / "products.db")

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    @patch("tapsi_garage.crawler.time.sleep")
    def test_empty_second_page_is_not_success(self, sleep):
        client = FakeClient(empty_second_page=True)
        with self.assertRaises(TapsiGarageError):
            crawl_products(client, self.store)
        self.assertEqual(client.second_page_calls, 4)
        row = self.store.conn.execute(
            "SELECT status FROM crawl_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertTrue(row["status"].startswith("aborted:"))

    @patch("tapsi_garage.crawler.time.sleep")
    def test_unexpected_exception_marks_run_aborted(self, sleep):
        with self.assertRaises(RuntimeError):
            crawl_products(FakeClient(crash=True), self.store)
        row = self.store.conn.execute(
            "SELECT status FROM crawl_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIn("RuntimeError", row["status"])

    @patch("tapsi_garage.crawler.time.sleep")
    def test_complete_crawl(self, sleep):
        result = crawl_products(FakeClient(), self.store)
        self.assertEqual(result["total"], 2)
        self.assertEqual(self.store.stats()["total"], 2)

    @patch("tapsi_garage.crawler.time.sleep")
    def test_save_failure_does_not_mark_run_done(self, sleep):
        with patch.object(self.store, "upsert_product", side_effect=ValueError("bad row")):
            with self.assertRaises(TapsiGarageError):
                crawl_products(FakeClient(), self.store)
        row = self.store.conn.execute(
            "SELECT status FROM crawl_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertTrue(row["status"].startswith("aborted:"))

    @patch("tapsi_garage.crawler.time.sleep")
    def test_empty_existing_catalog_is_not_success(self, sleep):
        self.store.upsert_product({"id": "saved", "title": "Saved", "cityId": 1})
        self.store.commit()
        client = FakeClient(empty_catalog=True)
        with self.assertRaises(TapsiGarageError):
            crawl_products(client, self.store)
        self.assertEqual(client.first_page_calls, 4)
        row = self.store.conn.execute(
            "SELECT status FROM crawl_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertTrue(row["status"].startswith("aborted:"))

    def test_list_payload_without_outer_pagination(self):
        client = TapsiGarageClient()
        with patch.object(client, "request", return_value={
            "payload": [{"productDetails": [{"id": "item"}]}]
        }):
            result = client.get_products(1)
        self.assertEqual(result["products"][0]["id"], "item")
        self.assertEqual(result["pagination"], {})

    def test_cli_paths_remove_directional_copy_artifacts(self):
        import main

        args = main.build_parser().parse_args([
            "export", "--json", "data/products.json\u2069.\u2069",
            "--csv", "data/products.csv\u2069",
        ])
        self.assertEqual(args.json, Path("data/products.json"))
        self.assertEqual(args.csv, Path("data/products.csv"))

    @patch("main.ProductStore")
    @patch("main.TapsiGarageClient")
    @patch("main.crawl_products", side_effect=TapsiGarageError("incomplete"))
    def test_cli_does_not_export_after_failed_crawl(self, crawl, client_class, store_class):
        import main

        store = MagicMock()
        store.stats.return_value = {"total": 1}
        store_class.return_value = store
        client_class.return_value.get_cities.return_value = []
        args = Namespace(city=1, category=None, subcategories=None, pages=None,
                         page_size=40, csv=Path("products.csv"),
                         json=Path("products.json"), csv_delimiter=",")
        with self.assertRaises(TapsiGarageError):
            main.cmd_crawl(args)
        store.export_csv.assert_not_called()
        store.export_json.assert_not_called()
        store.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
