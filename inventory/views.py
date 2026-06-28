from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from .models import Order, OrderItem, Product, Store, Inventory
from .serializers import (OrderCreateSerializer, OrderOutputSerializer ,OrderListSerializer , InventoryListSerializer ,ProductSearchSerializer)
from django.db.models import Sum
from django.shortcuts import get_object_or_404

from django.db.models import Q, OuterRef, Subquery, IntegerField
from django.core.paginator import Paginator, EmptyPage

from django.db.models import Case, When, IntegerField, Value

from django.core.cache import cache
from django.conf import settings
import time

from .tasks import send_order_confirmation

from drf_spectacular.utils import extend_schema, OpenApiParameter



class OrderCreateView(APIView):
   
    @extend_schema(
        summary="Create Order",
        description="Creates an order for a store. Auto CONFIRMED or REJECTED based on stock.",
        request=OrderCreateSerializer,
        responses={201: OrderOutputSerializer, 200: OrderOutputSerializer},
    )

    def post(self, request):
        # --- Step 1: Validate incoming data ---
        input_serializer = OrderCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                {"errors": input_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        validated      = input_serializer.validated_data
        store_id       = validated["store_id"]
        incoming_items = validated["items"]
        store          = Store.objects.get(id=store_id)

        with transaction.atomic():

            # --- Step 2: Validate all products exist ---
            product_ids = [item["product_id"] for item in incoming_items]
            products    = Product.objects.filter(id__in=product_ids)

            if products.count() != len(product_ids):
                found_ids   = set(products.values_list("id", flat=True))
                missing_ids = set(product_ids) - found_ids
                return Response(
                    {"errors": f"Products not found: {list(missing_ids)}"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # --- Step 3: Fetch inventory with row-level lock ---
            inventory_qs = Inventory.objects.select_for_update().filter(
                store=store,
                product_id__in=product_ids
            )
            inventory_map = {inv.product_id: inv for inv in inventory_qs}

            # --- Step 4: Check stock sufficiency ---
            insufficient = []

            for item in incoming_items:
                pid = item["product_id"]
                qty = item["quantity_requested"]
                inv = inventory_map.get(pid)

                if inv is None:
                    insufficient.append({
                        "product_id": pid,
                        "reason":     "Product not available in this store",
                        "available":  0,
                        "requested":  qty,
                    })
                elif inv.quantity < qty:
                    insufficient.append({
                        "product_id": pid,
                        "reason":     "Insufficient stock",
                        "available":  inv.quantity,
                        "requested":  qty,
                    })

            # --- Step 5: Create order ---
            if insufficient:
                # ANY failure → REJECTED, no stock deducted
                order = Order.objects.create(
                    store  = store,
                    status = Order.Status.REJECTED
                )
                for item in incoming_items:
                    OrderItem.objects.create(
                        order              = order,
                        product_id         = item["product_id"],
                        quantity_requested = item["quantity_requested"],
                    )

                # Fire async notification task
                send_order_confirmation.delay(order.id)

                response_data = OrderOutputSerializer(order).data
                response_data["insufficient_items"] = insufficient

                return Response(response_data, status=status.HTTP_200_OK)

            else:
                # ALL sufficient → deduct stock, CONFIRMED
                order = Order.objects.create(
                    store  = store,
                    status = Order.Status.CONFIRMED
                )

                for item in incoming_items:
                    pid = item["product_id"]
                    qty = item["quantity_requested"]

                    OrderItem.objects.create(
                        order              = order,
                        product_id         = pid,
                        quantity_requested = qty,
                    )

                    # Deduct from inventory
                    inv           = inventory_map[pid]
                    inv.quantity -= qty
                    inv.save()

                # Bust inventory cache since stock changed
                cache.delete(f"inventory_store_{store_id}")

                # Fire async notification task
                send_order_confirmation.delay(order.id)

                return Response(
                    OrderOutputSerializer(order).data,
                    status=status.HTTP_201_CREATED
                )
                
            


class StoreOrderListView(APIView):
    @extend_schema(
        summary="List Store Orders",
        description="Returns all orders for a store sorted by newest first.",
        responses={200: OrderListSerializer(many=True)},
        parameters=[
            OpenApiParameter("store_id", int, OpenApiParameter.PATH,
                           description="Store ID"),
        ]
    )

    def get(self, request, store_id):

        # Verify store exists — returns 404 automatically if not
        store = get_object_or_404(Store, id=store_id)

        orders = (
            Order.objects
            .filter(store=store)
            .annotate(
                # Sum of quantity_requested across all items in each order
                total_items=Sum("items__quantity_requested")
            )
            .order_by("-created_at")   # newest first
            # No select_related needed — store_name comes from
            # the store object we already have, not a DB join
        )

        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

    
class StoreInventoryListView(APIView):

    @extend_schema(
        summary="Store Inventory",
        description="Returns all inventory items for a store sorted alphabetically.",
        responses={200: InventoryListSerializer(many=True)},
    )

    def get(self, request, store_id):
        store = get_object_or_404(Store, id=store_id)

        # ── Cache key unique per store ────────────────────────────────────
        cache_key = f"inventory_store_{store_id}"

        # ── Try cache first ───────────────────────────────────────────────
        cached = cache.get(cache_key)
        if cached:
            return Response(cached, status=status.HTTP_200_OK)

        # ── Cache miss — hit the DB ───────────────────────────────────────
        inventory = (
            Inventory.objects
            .filter(store=store)
            .select_related("product__category")
            .order_by("product__title")
        )

        serializer = InventoryListSerializer(inventory, many=True)

        # ── Store in cache for 5 minutes ──────────────────────────────────
        cache.set(cache_key, serializer.data, timeout=settings.CACHE_TTL)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def invalidate_cache(self, store_id):
        cache.delete(f"inventory_store_{store_id}")
# class StoreInventoryListView(APIView):

#     def get(self, request, store_id):

#         # 404 if store doesn't exist
#         store = get_object_or_404(Store, id=store_id)

#         inventory = (
#             Inventory.objects
#             .filter(store=store)
#             .select_related("product__category")  # single JOIN — no N+1
#             .order_by("product__title")            # alphabetical by product title
#         )

#         serializer = InventoryListSerializer(inventory, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)
    


class ProductSearchView(APIView):

    @extend_schema(
        summary="Search Products",
        description="Full product search with filters, sorting and pagination.",
        responses={200: ProductSearchSerializer(many=True)},
        parameters=[
            OpenApiParameter("q",         str, description="Search keyword"),
            OpenApiParameter("category",  str, description="Filter by category name"),
            OpenApiParameter("price_min", float, description="Minimum price"),
            OpenApiParameter("price_max", float, description="Maximum price"),
            OpenApiParameter("store_id",  int, description="Store ID for stock quantity"),
            OpenApiParameter("in_stock",  str, description="true or false"),
            OpenApiParameter("sort_by",   str, description="price_asc, price_desc, newest, relevance"),
            OpenApiParameter("page",      int, description="Page number"),
            OpenApiParameter("page_size", int, description="Results per page"),
        ]
    )

    def get(self, request):

        # ── 1. Pull all query params ──────────────────────────────────────
        keyword    = request.query_params.get("q", "").strip()
        category   = request.query_params.get("category", "").strip()
        price_min  = request.query_params.get("price_min")
        price_max  = request.query_params.get("price_max")
        store_id   = request.query_params.get("store_id")
        in_stock   = request.query_params.get("in_stock", "").lower()
        sort_by    = request.query_params.get("sort_by", "relevance")  
        page       = int(request.query_params.get("page", 1))
        page_size  = int(request.query_params.get("page_size", 10))

        # ── 2. Base queryset with category join (always needed) ───────────
        qs = Product.objects.select_related("category")

        # ── 3. Keyword search across title, description, category name ────
        if keyword:
            qs = qs.filter(
                Q(title__icontains=keyword)       |
                Q(description__icontains=keyword) |
                Q(category__name__icontains=keyword)
            )

        # ── 4. Optional filters ───────────────────────────────────────────

        # Filter by category name
        if category:
            qs = qs.filter(category__name__icontains=category)

        # Filter by price range
        if price_min:
            try:
                qs = qs.filter(price__gte=float(price_min))
            except ValueError:
                return Response(
                    {"error": "price_min must be a valid number"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if price_max:
            try:
                qs = qs.filter(price__lte=float(price_max))
            except ValueError:
                return Response(
                    {"error": "price_max must be a valid number"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filter / annotate by store_id
        store = None
        if store_id:
            try:
                store = get_object_or_404(Store, id=int(store_id))
            except ValueError:
                return Response(
                    {"error": "store_id must be a valid integer"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Subquery: fetch quantity for this product in this store
            inventory_subquery = Inventory.objects.filter(
                store=store,
                product=OuterRef("pk")
            ).values("quantity")[:1]

            # Annotate each product with its quantity in the given store
            qs = qs.annotate(
                inventory_quantity=Subquery(
                    inventory_subquery,
                    output_field=IntegerField()
                )
            )

            # in_stock filter — only makes sense when store_id is provided
            if in_stock == "true":
                qs = qs.filter(inventory__store=store, inventory__quantity__gt=0)
            elif in_stock == "false":
                qs = qs.filter(
                    Q(inventory__store=store, inventory__quantity=0) |
                    ~Q(inventory__store=store)
                )

        # ── 5. Sorting ────────────────────────────────────────────────────
        SORT_MAP = {
            "price_asc":  "price",
            "price_desc": "-price",
            "newest":     "-id",       # use created_at if you add that field later
            "relevance":  "title",     # alphabetical as a proxy for relevance
        }
        order_field = SORT_MAP.get(sort_by, "title")
        qs = qs.order_by(order_field)

        # ── 6. Pagination ─────────────────────────────────────────────────
        paginator    = Paginator(qs, page_size)
        total_pages  = paginator.num_pages
        total_count  = paginator.count

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return Response(
                {"error": f"Page {page} does not exist. Total pages: {total_pages}"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ── 7. Serialize & respond ────────────────────────────────────────
        serializer = ProductSearchSerializer(page_obj.object_list, many=True)

        return Response({
            "pagination": {
                "total_count":   total_count,
                "total_pages":   total_pages,
                "current_page":  page,
                "page_size":     page_size,
                "has_next":      page_obj.has_next(),
                "has_previous":  page_obj.has_previous(),
            },
            "results": serializer.data
        }, status=status.HTTP_200_OK)
    


class ProductSuggestView(APIView):

    # ── Rate limit settings ───────────────────────────────────────────────
    RATE_LIMIT  = 20
    RATE_WINDOW = 60

    def get_client_ip(self, request):
        """Extract real IP even behind proxies"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def is_rate_limited(self, ip):
        cache_key     = f"rate_limit_suggest_{ip}"
        now           = int(time.time())
        window        = self.RATE_WINDOW
        request_times = cache.get(cache_key, [])
        request_times = [t for t in request_times if now - t < window]

        if len(request_times) >= self.RATE_LIMIT:
            return True

        request_times.append(now)
        cache.set(cache_key, request_times, timeout=window)
        return False

    @extend_schema(
        summary="Autocomplete Suggest",
        description="Returns up to 10 product title suggestions. Min 3 chars. Rate limited to 20 req/min.",
        responses={200: None},
        parameters=[
            OpenApiParameter("q", str, description="Search prefix (min 3 characters)"),
        ]
    )
    def get(self, request):
        # ── Rate limiting check ───────────────────────────────────────────
        ip = self.get_client_ip(request)

        if self.is_rate_limited(ip):
            return Response(
                {
                    "error":       "Rate limit exceeded.",
                    "message":     "Max 20 requests per minute allowed.",
                    "retry_after": "60 seconds"
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        q = request.query_params.get("q", "").strip()

        # ── Minimum 3 characters ──────────────────────────────────────────
        if len(q) < 3:
            return Response(
                {"error": "Query must be at least 3 characters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Cache key per search term ─────────────────────────────────────
        cache_key = f"suggest_{q.lower()}"
        cached    = cache.get(cache_key)

        if cached:
            return Response(
                {"q": q, "suggestions": cached, "source": "cache"},
                status=status.HTTP_200_OK
            )

        # ── DB query ──────────────────────────────────────────────────────
        qs = (
            Product.objects
            .filter(title__icontains=q)
            .annotate(
                sort_order=Case(
                    When(title__istartswith=q, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("sort_order", "title")
            .values("title")
            [:10]
        )

        suggestions = [item["title"] for item in qs]

        # ── Cache results for 5 minutes ───────────────────────────────────
        cache.set(cache_key, suggestions, timeout=settings.CACHE_TTL)

        return Response(
            {"q": q, "suggestions": suggestions, "source": "db"},
            status=status.HTTP_200_OK
        )