"""Tapsi Garage crawler & cart client.

کراولر سایت تپسی گاراژ (https://tapsi-garage.ir) به همراه قابلیت افزودن
محصولات به سبد خرید (Basket) با استفاده از API رسمی خود سایت.
"""

__version__ = "1.0.0"

from .client import TapsiGarageClient  # noqa: F401
from .cart import Cart, AddResult  # noqa: F401
