import random
from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from inventory.models import Category, Product, Store, Inventory

fake = Faker()


class Command(BaseCommand):
    help = "Seed the database with dummy data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding",
        )

    def handle(self, *args, **options):

        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing existing data..."))
            Inventory.objects.all().delete()
            Product.objects.all().delete()
            Store.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing data cleared.\n"))

        with transaction.atomic():
            categories = self._seed_categories()
            products   = self._seed_products(categories)
            stores     = self._seed_stores()
            self._seed_inventory(stores, products)

        self.stdout.write(self.style.SUCCESS("\nSeeding complete!"))
        self.stdout.write(f"  Categories : {Category.objects.count()}")
        self.stdout.write(f"  Products   : {Product.objects.count()}")
        self.stdout.write(f"  Stores     : {Store.objects.count()}")
        self.stdout.write(f"  Inventory  : {Inventory.objects.count()}")

    # ── 1. Categories ─────────────────────────────────────────────────────
    def _seed_categories(self):
        self.stdout.write("Seeding categories...")

        CATEGORY_NAMES = [
            "Electronics", "Mobile Phones", "Laptops & Computers",
            "Audio & Headphones", "Cameras", "Home Appliances",
            "Kitchen Appliances", "Furniture", "Clothing & Fashion",
            "Footwear", "Sports & Outdoors", "Books & Stationery",
            "Toys & Games", "Beauty & Personal Care", "Health & Wellness",
            "Groceries", "Automotive", "Tools & Hardware",
            "Garden & Outdoors", "Baby & Kids",
        ]

        categories = []
        for name in CATEGORY_NAMES:
            cat, _ = Category.objects.get_or_create(name=name)
            categories.append(cat)

        self.stdout.write(self.style.SUCCESS(f"  {len(categories)} categories created."))
        return categories

    # ── 2. Products ───────────────────────────────────────────────────────
    def _seed_products(self, categories):
        self.stdout.write("Seeding products...")

        # Realistic product title templates per category
        PRODUCT_TEMPLATES = {
            "Electronics":            ["Smart TV {size}\"", "LED Monitor {size}\"", "UPS {model}", "Power Bank {capacity}mAh"],
            "Mobile Phones":          ["{brand} Phone {model}", "{brand} Smartphone Pro", "{brand} {model} 5G"],
            "Laptops & Computers":    ["{brand} Laptop {size}\"", "{brand} Gaming PC", "{brand} Chromebook"],
            "Audio & Headphones":     ["{brand} Wireless Earbuds", "{brand} Over-Ear Headphones", "{brand} Speaker"],
            "Cameras":                ["{brand} DSLR {model}", "{brand} Mirrorless Camera", "{brand} Action Cam"],
            "Home Appliances":        ["{brand} Washing Machine", "{brand} Refrigerator", "{brand} Air Conditioner"],
            "Kitchen Appliances":     ["{brand} Microwave", "{brand} Blender", "{brand} Air Fryer", "{brand} Toaster"],
            "Furniture":              ["{style} Sofa", "{style} Dining Table", "{style} Bookshelf", "{style} Wardrobe"],
            "Clothing & Fashion":     ["{style} {color} T-Shirt", "{style} Jacket", "{style} Jeans", "{color} Dress"],
            "Footwear":               ["{brand} Running Shoes", "{brand} Sneakers", "{brand} Boots", "{brand} Sandals"],
            "Sports & Outdoors":      ["{brand} Yoga Mat", "{brand} Dumbbells Set", "{brand} Treadmill", "Camping Tent"],
            "Books & Stationery":     ["Notebook Pack", "Ballpoint Pens Set", "Sketchbook", "Planner {year}"],
            "Toys & Games":           ["LEGO Set {model}", "Board Game", "RC Car", "Puzzle {pieces} pieces"],
            "Beauty & Personal Care": ["{brand} Face Cream", "{brand} Shampoo", "{brand} Perfume", "Hair Dryer"],
            "Health & Wellness":      ["Vitamin {type} Supplements", "Protein Powder", "Yoga Block Set", "Massage Gun"],
            "Groceries":              ["Organic {item}", "Premium {item}", "Fresh {item} Pack"],
            "Automotive":             ["Car Phone Mount", "Dash Cam", "Car Vacuum Cleaner", "Tire Inflator"],
            "Tools & Hardware":       ["Cordless Drill", "Toolbox Set", "Electric Saw", "Measuring Tape"],
            "Garden & Outdoors":      ["Garden Hose", "Plant Pots Set", "Lawn Mower", "Garden Gloves"],
            "Baby & Kids":            ["Baby Monitor", "Stroller", "Baby Carrier", "Kids Backpack"],
        }

        BRANDS  = ["Samsung", "Apple", "Sony", "LG", "Xiaomi", "HP", "Dell", "Bosch", "Nike", "Adidas"]
        STYLES  = ["Modern", "Classic", "Vintage", "Minimalist", "Luxury", "Casual"]
        COLORS  = ["Red", "Blue", "Black", "White", "Green", "Grey", "Navy"]
        SIZES   = [24, 27, 32, 43, 55, 65]
        TYPES   = ["C", "D", "B12", "Zinc", "Iron", "Omega-3"]
        ITEMS   = ["Olive Oil", "Honey", "Almonds", "Green Tea", "Oats"]
        PIECES  = [100, 250, 500, 1000]

        def resolve_template(template):
            return template.format(
                brand    = random.choice(BRANDS),
                model    = fake.bothify(text="??-###").upper(),
                style    = random.choice(STYLES),
                color    = random.choice(COLORS),
                size     = random.choice(SIZES),
                capacity = random.choice([5000, 10000, 20000, 30000]),
                type     = random.choice(TYPES),
                item     = random.choice(ITEMS),
                pieces   = random.choice(PIECES),
                year     = random.choice([2024, 2025, 2026]),
            )

        products = []
        TARGET   = 1000

        # Calculate how many products per category to hit 1000+
        per_category = TARGET // len(PRODUCT_TEMPLATES)

        for category in Category.objects.all():
            templates = PRODUCT_TEMPLATES.get(category.name, ["Generic Product {model}"])

            for _ in range(per_category):
                template = random.choice(templates)
                title    = resolve_template(template)

                product = Product(
                    title       = title,
                    description = fake.paragraph(nb_sentences=3),
                    price       = round(random.uniform(5.00, 2000.00), 2),
                    category    = category,
                )
                products.append(product)

        # Bulk insert — much faster than individual .save() calls
        created = Product.objects.bulk_create(products, batch_size=200)

        self.stdout.write(self.style.SUCCESS(f"  {len(created)} products created."))
        return created

    # ── 3. Stores ─────────────────────────────────────────────────────────
    def _seed_stores(self):
        self.stdout.write("Seeding stores...")

        STORE_NAMES = [
            "Aforro Central", "Aforro North", "Aforro South",
            "Aforro East",    "Aforro West",  "Aforro Express",
            "Aforro Plus",    "Aforro Mall",  "Aforro Outlet",
            "Aforro Hub",     "Aforro Market","Aforro Depot",
            "Aforro Mega",    "Aforro City",  "Aforro Square",
            "Aforro Point",   "Aforro Zone",  "Aforro Corner",
            "Aforro Park",    "Aforro Prime",
        ]

        stores = []
        for name in STORE_NAMES:
            store, _ = Store.objects.get_or_create(
                name     = name,
                defaults = {"location": fake.address().replace("\n", ", ")}
            )
            stores.append(store)

        self.stdout.write(self.style.SUCCESS(f"  {len(stores)} stores created."))
        return stores

    # ── 4. Inventory ──────────────────────────────────────────────────────
    def _seed_inventory(self, stores, products):
        self.stdout.write("Seeding inventory (this may take a moment)...")

        all_products    = list(Product.objects.all())
        total_products  = len(all_products)
        inventory_rows  = []

        # Track (store_id, product_id) pairs to avoid unique_together violation
        seen = set()

        for store in Store.objects.all():

            # Pick 300+ random products for this store (no duplicates per store)
            count    = random.randint(300, min(500, total_products))
            selected = random.sample(all_products, count)

            for product in selected:
                key = (store.id, product.id)
                if key in seen:
                    continue
                seen.add(key)

                inventory_rows.append(
                    Inventory(
                        store    = store,
                        product  = product,
                        quantity = random.randint(0, 200),
                    )
                )

        # Bulk insert in batches — handles 20 stores × 400 products = 8000 rows
        Inventory.objects.bulk_create(inventory_rows, batch_size=500 , ignore_conflicts = True)

        self.stdout.write(self.style.SUCCESS(f"  {len(inventory_rows)} inventory rows created."))