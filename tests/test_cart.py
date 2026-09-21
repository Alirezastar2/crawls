"""Regression tests for explicit vendor selection."""

import unittest

from tapsi_garage.cart import Cart


class FakeClient:
    def get_product_detail(self, product_id, city_id):
        return {"categoryId": 7}

    def get_product_vendors(self, *args, **kwargs):
        return [{"id": "different", "title": "Different"}]

    def add_basket_item(self, **kwargs):
        raise AssertionError("must not add via a different vendor")


class CartTest(unittest.TestCase):
    def test_explicit_missing_vendor_is_not_replaced(self):
        result = Cart(FakeClient()).add("product", vendor_id="requested")
        self.assertFalse(result.ok)
        self.assertIn("requested", result.message)


if __name__ == "__main__":
    unittest.main()
