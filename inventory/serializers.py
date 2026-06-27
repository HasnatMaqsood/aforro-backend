from rest_framework import serializers
from .models import Order, OrderItem, Product, Store, Inventory


# ── Order Creation (Input) ─────────────────────────────────────────────────
class OrderItemInputSerializer(serializers.Serializer):
    product_id         = serializers.IntegerField()
    quantity_requested = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    store_id = serializers.IntegerField()
    items    = OrderItemInputSerializer(many=True, min_length=1)

    def validate_store_id(self, value):
        if not Store.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Store with id {value} does not exist.")
        return value

    def validate_items(self, value):
        if len(value) == 0:
            raise serializers.ValidationError("Order must have at least one item.")
        product_ids = [item["product_id"] for item in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Duplicate products in order items are not allowed.")
        return value


# ── Order Output ───────────────────────────────────────────────────────────
class OrderItemOutputSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title")
    product_id    = serializers.IntegerField(source="product.id")

    class Meta:
        model  = OrderItem
        fields = ["product_id", "product_title", "quantity_requested"]


class OrderOutputSerializer(serializers.ModelSerializer):
    items      = OrderItemOutputSerializer(many=True)
    store_name = serializers.CharField(source="store.name")

    class Meta:
        model  = Order
        fields = ["id", "store_name", "status", "created_at", "items"]


# ── Order List ─────────────────────────────────────────────────────────────
class OrderListSerializer(serializers.ModelSerializer):
    store_name  = serializers.CharField(source="store.name")
    total_items = serializers.IntegerField()

    class Meta:
        model  = Order
        fields = ["id", "store_name", "status", "created_at", "total_items"]


# ── Inventory List ─────────────────────────────────────────────────────────
class InventoryListSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title")
    price         = serializers.DecimalField(
                        source="product.price",
                        max_digits=10,
                        decimal_places=2
                    )
    category_name = serializers.CharField(source="product.category.name")

    class Meta:
        model  = Inventory
        fields = ["product_title", "price", "category_name", "quantity"]


# ── Product Search ─────────────────────────────────────────────────────────
class ProductSearchSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name")
    quantity      = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = ["id", "title", "description", "price", "category_name", "quantity"]

    def get_quantity(self, obj):
        return getattr(obj, "inventory_quantity", None)