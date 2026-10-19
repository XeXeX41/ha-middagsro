"""Constants for the REMA 1000 integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "middagsro"

LIST_SCAN_INTERVAL: Final = timedelta(minutes=2)
OFFERS_SCAN_INTERVAL: Final = timedelta(hours=3)

STORAGE_VERSION: Final = 1

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_QUERY: Final = "query"
ATTR_LIMIT: Final = "limit"
ATTR_ITEMS: Final = "items"
ATTR_PRODUCT_ID: Final = "product_id"
ATTR_NAME: Final = "name"
ATTR_AMOUNT: Final = "amount"
ATTR_CATALOG: Final = "catalog"

SERVICE_SEARCH_PRODUCTS: Final = "search_products"
SERVICE_ADD_ITEMS: Final = "add_items"
SERVICE_GET_OFFERS: Final = "get_offers"
SERVICE_GENERATE_MEAL_PLAN: Final = "generate_meal_plan"
SERVICE_SEND_MEAL_PLAN: Final = "send_meal_plan"
SERVICE_GENERATE_DAILY_SUGGESTIONS: Final = "generate_daily_suggestions"
