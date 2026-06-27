from django.contrib import admin
from .models import Category, Product, Store, Inventory, Order, OrderItem

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Store)
admin.site.register(Inventory)
admin.site.register(Order)
admin.site.register(OrderItem)