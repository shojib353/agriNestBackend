from django.contrib import admin
from .models import Category, FavoriteProduct, OrderStatusHistory, Product, ProductImage, ProductOffer, ProductReview, Order, OrderItem

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    # Automatically fills out the slug field as you type the category name
    prepopulated_fields = {'slug': ('name',)} 
    search_fields = ('name',)

# --- PRODUCT SECTION ---

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1  # Shows one empty row for uploading a new image

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id','title', 'category', 'seller','discounted_price','discount', 'price', 'weight', 'stock', 'is_active', 'is_popular','delivery_time', 'delivery_type', 'delivery_cost', 'created_at')
    list_filter = ('is_active', 'category', 'unit', 'created_at')
    search_fields = ('title', 'description')
    list_editable = ('price', 'weight', 'stock', 'delivery_cost','discount', 'delivery_time', 'delivery_type', 'is_active', 'is_popular')  # Edit these directly from the list view!
    inlines = [ProductImageInline]

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__title', 'user__username', 'review')

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    # Display the financial breakdown clearly
    fields = ('product', 'quantity', 'product_price_after_discount', 'product_delivery_cost', 'item_total')
    
    # Make all fields read-only to protect historical transaction integrity
    readonly_fields = ('product', 'quantity', 'product_price_after_discount', 'product_delivery_cost', 'item_total')
    
    # Prevent admins from deleting or adding items manually, 
    # as this would desync the Order's grand total calculated in your serializer.
    can_delete = False 

    def item_total(self, obj):
        if obj.product_price_after_discount is not None and obj.product_delivery_cost is not None:
            return (obj.product_price_after_discount + obj.product_delivery_cost) * obj.quantity
        return 0
    item_total.short_description = "Line Total (Inc. Delivery)"

    def has_add_permission(self, request, obj=None):
        return False # Force orders to be created via your API serializer
    
@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'timestamp')
    list_filter = ('status', 'timestamp')
    readonly_fields = ('order', 'status', 'timestamp')
    search_fields = ('order__id',)

class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('order', 'status', 'timestamp')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'buyer', 'seller', 'status', 'payment_type', 
        'delivery_location', 'total_amount', 'created_at', 'tracking_number'
    )
    list_filter = ('status', 'payment_type', 'created_at', 'seller')
    search_fields = ('id', 'buyer__username', 'buyer__email', 'seller__username')
    list_editable = ('status',)
    
    # Adds a helpful date-based drill-down navigation at the top of the list view
    date_hierarchy = 'created_at' 
    
    # Lock down the calculated and relation fields
    readonly_fields = ('buyer', 'seller', 'total_amount', 'created_at')
    
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    
    # Group fields logically. Tuples put fields on the same line.
    fieldsets = (
        ('Order Parties', {
            'fields': (('buyer', 'seller'),)
        }),
        ('Financials & Status', {
            'fields': ('total_amount', 'status', 'payment_type', 'created_at')
        }),
        ('Delivery Details', {
            'fields': ('delivery_location',)
        }),
        ('Cancellations', {
            'fields': ('cancel_reason',),
            'classes': ('collapse',) 
        }),
    )

    # Example Bulk Actions to speed up order management
    actions = ['mark_as_shipped', 'mark_as_delivered']

    @admin.action(description='Mark selected orders as Shipped')
    def mark_as_shipped(self, request, queryset):
        # Update with whatever your actual choice string is for shipped status
        updated_count = queryset.update(status='Shipped')
        self.message_user(request, f'{updated_count} order(s) marked as Shipped.')

    @admin.action(description='Mark selected orders as Delivered')
    def mark_as_delivered(self, request, queryset):
        # Update with whatever your actual choice string is for delivered status
        updated_count = queryset.update(status='Delivered')
        self.message_user(request, f'{updated_count} order(s) marked as Delivered.')
        actions = ['mark_as_shipped', 'mark_as_delivered']

    # ✅ IMPORTANT PART (STATUS HISTORY TRACKING)
    def save_model(self, request, obj, form, change):
        old_status = None

        if change:
            old_status = Order.objects.get(pk=obj.pk).status

        super().save_model(request, obj, form, change)

        # Create history only if status changed
        if change and old_status != obj.status:
            OrderStatusHistory.objects.create(
                order=obj,
                status=obj.status
            )

@admin.register(ProductOffer)
class ProductOfferAdmin(admin.ModelAdmin):
    list_display = ('product', 'seller', 'discount_percentage')
    list_filter = ('seller', 'start_date', 'end_date')
    search_fields = ('title',)

@admin.register(FavoriteProduct)
class FavoriteProductAdmin(admin.ModelAdmin):
    list_display = ('user', 'product')
    list_filter = ('user', 'product')


from django.contrib import admin
from .models import Cart, CartItem

# Inline CartItem display inside Cart admin
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('total_price',)
    fields = ('product', 'quantity', 'total_price')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'total_price')
    search_fields = ('user__username', 'user__email')
    list_filter = ('created_at',)
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart','cart_id', 'product', 'quantity', 'total_price')
    search_fields = ('product__title', 'cart__user__username')
    list_filter = ('cart__created_at',)