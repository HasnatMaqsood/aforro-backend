from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


# ── Task 1: Order Confirmation Notification ────────────────────────────────
@shared_task(bind=True, max_retries=3)
def send_order_confirmation(self, order_id):
    """
    Triggered after every order is created.
    Simulates sending confirmation email/SMS.
    In production: integrate with SendGrid, Twilio, etc.
    """
    try:
        from .models import Order

        order = Order.objects.select_related("store").prefetch_related("items__product").get(id=order_id)

        # Simulate sending notification
        logger.info(f"[ORDER CONFIRMATION] Order #{order.id}")
        logger.info(f"  Store   : {order.store.name}")
        logger.info(f"  Status  : {order.status}")
        logger.info(f"  Items   : {order.items.count()}")
        logger.info(f"  Time    : {order.created_at}")

        # Build summary
        item_summary = []
        for item in order.items.all():
            item_summary.append(
                f"{item.product.title} x {item.quantity_requested}"
            )

        logger.info(f"  Products: {', '.join(item_summary)}")
        logger.info(f"[ORDER CONFIRMATION] Notification sent for Order #{order.id}")

        return {
            "status":   "sent",
            "order_id": order_id,
            "store":    order.store.name,
            "items":    item_summary,
        }

    except Exception as exc:
        logger.error(f"Failed to send confirmation for Order #{order_id}: {exc}")
        # Retry after 5 seconds, max 3 times
        raise self.retry(exc=exc, countdown=5)


# ── Task 2: Daily Inventory Summary ───────────────────────────────────────
@shared_task
def generate_daily_inventory_summary():
    """
    Runs daily to summarize inventory health.
    Shows low stock, out of stock, and healthy items per store.
    In production: email this report to managers.
    """
    from .models import Store, Inventory

    logger.info("[INVENTORY SUMMARY] Starting daily report...")
    logger.info(f"  Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}")

    stores  = Store.objects.all()
    report  = []

    for store in stores:
        inventory = Inventory.objects.filter(store=store)

        out_of_stock  = inventory.filter(quantity=0).count()
        low_stock     = inventory.filter(quantity__gt=0, quantity__lte=10).count()
        healthy       = inventory.filter(quantity__gt=10).count()
        total         = inventory.count()

        store_report = {
            "store":        store.name,
            "total_items":  total,
            "out_of_stock": out_of_stock,
            "low_stock":    low_stock,
            "healthy":      healthy,
        }
        report.append(store_report)

        logger.info(f"\n  Store : {store.name}")
        logger.info(f"    Total     : {total}")
        logger.info(f"    Healthy   : {healthy}")
        logger.info(f"    Low Stock : {low_stock}")
        logger.info(f"    Out       : {out_of_stock}")

    logger.info("[INVENTORY SUMMARY] Report complete.")
    return report


# ── Task 3: Preprocess Products for Search ────────────────────────────────
@shared_task
def preprocess_products_for_search():
    """
    Preprocesses and caches product search data.
    Warms up the cache so first search is instant.
    """
    from .models import Product
    from django.core.cache import cache

    logger.info("[SEARCH PREPROCESS] Warming up search cache...")

    # Common search prefixes to pre-cache
    COMMON_PREFIXES = [
        "sam", "app", "son", "lap", "pho",
        "cam", "tab", "ear", "key", "mou",
    ]

    from django.db.models import Case, When, IntegerField, Value, Q

    warmed = 0
    for prefix in COMMON_PREFIXES:
        cache_key = f"suggest_{prefix.lower()}"

        # Skip if already cached
        if cache.get(cache_key):
            continue

        qs = (
            Product.objects
            .filter(title__icontains=prefix)
            .annotate(
                sort_order=Case(
                    When(title__istartswith=prefix, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("sort_order", "title")
            .values("title")[:10]
        )

        suggestions = [item["title"] for item in qs]
        cache.set(cache_key, suggestions, timeout=60 * 10)  # 10 min
        warmed += 1

    logger.info(f"[SEARCH PREPROCESS] Warmed {warmed} cache keys.")
    return {"warmed": warmed, "prefixes": COMMON_PREFIXES}