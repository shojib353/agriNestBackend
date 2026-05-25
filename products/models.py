import uuid

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class Category(models.Model):
    
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.ImageField(upload_to='categories/', blank=True, null=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    class Unit(models.TextChoices):
        KG = 'kg', 'Kilogram'
        LT = 'lt', 'Liter'
        PIECE = 'piece', 'Piece'
    class DeliveryTime(models.TextChoices):
        MIN_20_30 = '20-30_min', '20-30 minutes'
        MIN_30_60 = '30-60_min', '30-60 minutes'
        MIN_60_90 = '60-90_min', '60-90 minutes'
        HOURS_2_4 = '2-4_hours', '2-4 hours'
        SAME_DAY = 'today_day', 'Today Day Delivery'
        NEXT_DAY = 'next_day', 'Next Day Delivery'
        NEXT_MONTH = 'next_month', 'Next Month Delivery'

    class DeliveryType(models.TextChoices):
        HOME_DELIVERY = 'home_delivery', 'Home Delivery'
        PICKUP = 'pickup', 'Pickup'
        FREE_DELIVERY = 'free_delivery', 'Free Delivery'


    # Note: Make sure you have an 'accounts' app with a 'SellerProfile' model!
    seller = models.ForeignKey(
        'agriAuthentication.SellerProfile', on_delete=models.CASCADE, related_name='products'
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name='products'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    warning = models.TextField(null=True, blank=True)
    terms_of_use = models.TextField(null=True, blank=True)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.KG)
    weight = models.DecimalField(max_digits=10, decimal_places=2, help_text="Weight in the specified unit")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Discount percentage 0-100'
    )
    stock = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10000)])
    is_active = models.BooleanField(default=True)
    delivery_time = models.CharField(
        max_length=50, 
        choices=DeliveryTime.choices,
        null=True, 
        blank=True, 
        help_text="Estimated delivery time"
    )
    
    delivery_type = models.CharField(
        max_length=50, 
        choices=DeliveryType.choices,
        null=True, 
        blank=True, 
        help_text="Delivery type"
    )
    
    delivery_cost = models.IntegerField(
        default=0,
        help_text="Delivery cost (e.g., in BDT or your local currency)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_popular = models.BooleanField(default=False, help_text="Mark as popular product")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def discounted_price(self):
        # 1. Calculate the base discounted price using the Product's discount field
        # Using Decimal formula: price - (price * discount / 100) to avoid float errors
        base_discounted_price = self.price - (self.price * (self.discount / 100))

        # 2. Check if a ProductOffer exists for this product
        if hasattr(self, 'offers'):
            offer = self.offers
            now = timezone.now()

            # 3. Check if the offer is currently active based on dates
            if offer.start_date <= now <= offer.end_date:
                # Calculate the price using the offer's discount percentage
                offer_discounted_price = self.price - (self.price * (offer.discount_percentage / 100))

                # 4. If the offer price is lower than the base discounted price, return it
                if offer_discounted_price < base_discounted_price:
                    return offer_discounted_price

        # 5. If no active offer exists, or the offer price isn't lower, return the base price
        return base_discounted_price

    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if not reviews:
            return 0
        return sum(r.rating for r in reviews) / reviews.count()
        
    @property
    def review_count(self):
        return self.reviews.count()


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.product.title} Image"

class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField( validators=[MinValueValidator(1), MaxValueValidator(5)])   # 1-5
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']


    def __str__(self):
        return f'{self.user} rated {self.product} {self.rating}★'
    
 
class FavoriteProduct(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)






    #order model



class Order(models.Model):
    PAYMENT_CHOICES = [
        ('cash', 'Cash on Delivery'),
        ('online', 'Online Payment'),
    ]

    STATUS_CHOICES = [
        ('order_placed', 'Order Placed'),
        ('preparing_shipment', 'Preparing Shipment'),
        ('ready_for_pickup', 'Ready for Pickup'),
        ('picked_up', 'Picked Up by Courier'),
        ('sorting_facility', 'At Sorting Facility'),
        ('departed_sorting', 'Departed Sorting Facility'),
        ('delivery_hub', 'Arrived at Delivery Hub'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'), 
    ]
    tracking_number = models.CharField(max_length=100, unique=True, null=True, blank=True)

    # Users involved
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchased_orders')
    seller = models.ForeignKey('agriAuthentication.SellerProfile', on_delete=models.CASCADE, related_name='sales_orders')
    
    # Order details
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total price at time of purchase")
    
    # Locations
    delivery_location = models.TextField(help_text="Where the product is being delivered")
    
    # Payment and Status
    payment_type = models.CharField(max_length=10, choices=PAYMENT_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='order_placed')
    cancel_reason = models.TextField(null=True, blank=True, help_text="Reason for cancelling the order")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # We removed self.product.title and replaced it with self.buyer
        return f"Order #{self.id} by {self.buyer} ({self.get_status_display()})"
    def generate_tracking_number(self):
        return f"ORD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            while True:
                new_tracking = self.generate_tracking_number()
                if not Order.objects.filter(tracking_number=new_tracking).exists():
                    self.tracking_number = new_tracking
                    break
        super().save(*args, **kwargs)
    
    
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)    
    product_price_after_discount = models.DecimalField(max_digits=10, decimal_places=2,blank=True, null=True)
    product_delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.quantity}x {self.product.title} (Order #{self.order.id})"
    
class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=30, choices=Order.STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order.tracking_number} - {self.status}"

class ProductOffer(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='offers',)
    seller = models.ForeignKey('agriAuthentication.SellerProfile', on_delete=models.CASCADE, related_name='offers')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    def __str__(self):
        return f"{self.title} - {self.discount_percentage}% off on {self.product.title if self.product else 'All Products'}"

class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carts'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart of {self.user}"

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'product')

    def __str__(self):
        return f"{self.quantity}x {self.product.title}"

    @property
    def total_price(self):
        return self.product.discounted_price * self.quantity
    @property
    def delivery_cost(self):
        return self.product.delivery_cost