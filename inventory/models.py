from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Product(models.Model):
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price       = models.DecimalField(max_digits=10, decimal_places=2)
    category    = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products"
    )

    def __str__(self):
        return self.title


class Store(models.Model):
    name     = models.CharField(max_length=255)
    location = models.CharField(max_length=500)

    def __str__(self):
        return self.name


class Inventory(models.Model):
    store    = models.ForeignKey(Store,   on_delete=models.CASCADE, related_name="inventory")
    product  = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="inventory")
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("store", "product")

    def __str__(self):
        return f"{self.store.name} - {self.product.title} ({self.quantity})"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING   = "PENDING",   "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        REJECTED  = "REJECTED",  "Rejected"

    store      = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="orders")
    status     = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.pk} [{self.status}] - {self.store.name}"


class OrderItem(models.Model):
    order              = models.ForeignKey(Order,   on_delete=models.CASCADE, related_name="items")
    product            = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity_requested = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product.title} x {self.quantity_requested} (Order #{self.order.pk})"