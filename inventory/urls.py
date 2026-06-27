from django.urls import path
from .views import (
    OrderCreateView,
    StoreOrderListView,
    StoreInventoryListView,
    ProductSearchView,
    ProductSuggestView,
)

urlpatterns = [
    path("orders/",                          OrderCreateView.as_view(),        name="order-create"),
    path("stores/<int:store_id>/orders/",    StoreOrderListView.as_view(),     name="store-order-list"),
    path("stores/<int:store_id>/inventory/", StoreInventoryListView.as_view(), name="store-inventory-list"),
    path("search/products/",                 ProductSearchView.as_view(),      name="product-search"),
    path("search/suggest/",                  ProductSuggestView.as_view(),     name="product-suggest"),
]