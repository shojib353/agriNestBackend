from rest_framework import serializers
from agriAuthentication.serializers import SellerProfileSerializer
from products.firebase_service import send_order_status_notification
from .models import Cart, CartItem, Category, Order, OrderItem, OrderStatusHistory, Product, ProductImage, ProductOffer, ProductReview
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist


User = get_user_model()

class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'role', 'photo']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon']

    # Optional: extra validation for case-insensitive uniqueness
    def validate_name(self, value):
        if Category.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Category with this name already exists.")
        return value




# Nested serializer for images
class ProductImageSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ProductImage
        fields = fields = '__all__'




# Nested serializer for reviews
class ProductReviewSerializer(serializers.ModelSerializer):
    user = UserDetailSerializer(read_only=True)
    class Meta:
        model = ProductReview
        fields = '__all__'
        read_only_fields = ['user', 'product']






class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ProductReviewSerializer(many=True, read_only=True)
    discounted_price = serializers.ReadOnlyField(read_only=True)
    discount = serializers.SerializerMethodField()   
    average_rating = serializers.ReadOnlyField(read_only=True)
    review_count = serializers.ReadOnlyField(read_only=True)
    is_favorited = serializers.SerializerMethodField(read_only=True)
    # seller_location = serializers.SerializerMethodField(read_only=True)  
    # seller_shop_name = serializers.SerializerMethodField(read_only=True) 
    seller_details = SellerProfileSerializer(source='seller', read_only=True) 
    product_is_in_cart = serializers.SerializerMethodField(read_only=True)
    delivery_time = serializers.ChoiceField(choices=Product.DeliveryTime.choices, required=False, allow_null=True)
    delivery_type = serializers.ChoiceField(choices=Product.DeliveryType.choices, required=False, allow_null=True)
    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['seller']

    def get_discount(self, obj):
            max_discount = obj.discount
            print(f"\n--- DEBUGGING DISCOUNT FOR: {obj.title} ---")
            print(f"Standard Discount: {max_discount}%")

            try:
                # In Django, trying to access a missing OneToOne reverse relation 
                # throws an ObjectDoesNotExist error. try/except is safer than hasattr.
                offer = obj.offers
                now = timezone.now()
                
                print(f"Offer Found! Offer Discount: {offer.discount_percentage}%")
                print(f"Start Date: {offer.start_date}")
                print(f"Current Now: {now}")
                print(f"End Date:   {offer.end_date}")

                if offer.start_date <= now <= offer.end_date:
                    print("Status: Offer is ACTIVE based on time.")
                    if offer.discount_percentage > max_discount:
                        print("Result: Offer is higher! Overriding standard discount.")
                        max_discount = offer.discount_percentage
                    else:
                        print("Result: Standard discount is still higher.")
                else:
                    print("Status: Offer is INACTIVE (Current time is not between start and end).")

            except ObjectDoesNotExist:
                print("Status: No offer found attached to this specific product.")

            print(f"FINAL DISCOUNT RETURNED: {max_discount}%\n")
            return max_discount

    def get_is_favorited(self, obj):
        user = self.context['request'].user
        if user.is_authenticated:
            return obj.favorited_by.filter(user=user).exists()
        return False
    def get_seller_location(self, obj): 
        try:
            return obj.seller.location
        except AttributeError:
            return 'Unknown'
    def get_seller_shop_name(self, obj): 
        try:
            return obj.seller.shop_name
        except AttributeError:
            return 'Unknown'
    def get_product_is_in_cart(self, obj):
        request = self.context.get('request')

        if not request or not request.user.is_authenticated:
            return False

        return CartItem.objects.filter(
            cart__user=request.user,
            product=obj
        ).exists()












#order serializer


class OrderItemSerializer(serializers.ModelSerializer):
    product_image = serializers.SerializerMethodField(read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['product','product_image' , 'product_title', 'quantity', 'product_price_after_discount', 'product_delivery_cost']
    def get_product_image(self, obj):
        request = self.context.get('request')  
        first_image = obj.product.images.first()
        if first_image and first_image.image:
            # build absolute URL
            return request.build_absolute_uri(first_image.image.url)
        return None
    
class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['status', 'timestamp']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True) # Nested items
    order_status_history = serializers.SerializerMethodField(read_only=True)
    seller_details = SellerProfileSerializer(source='seller', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'items', 'delivery_location', 'payment_type', 'tracking_number', 'total_amount', 'status', 'created_at', 'order_status_history', 'seller_details']
        read_only_fields = ['buyer', 'seller', 'tracking_number', 'status', 'created_at']
    
    def get_order_status_history(self, obj):
        history = OrderStatusHistory.objects.filter(order=obj).order_by('timestamp')
        return OrderStatusHistorySerializer(history, many=True).data

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        if not items_data:
            raise serializers.ValidationError({"items": "Order must contain at least one item."})

        # 1. Validate that all products belong to the SAME seller
        first_product = items_data[0]['product']
        seller = first_product.seller

        for item in items_data:
            if item['product'].seller != seller:
                raise serializers.ValidationError({
                    "items": "All products in a single order must belong to the same seller."
                })

        # 2. Check stock and calculate grand total
        grand_total = 0
        for item in items_data:
            product = item['product']
            quantity = item['quantity']
            product_price_after_discount = item['product_price_after_discount']
            product_delivery_cost = item['product_delivery_cost']

            if product.stock < quantity:
                raise serializers.ValidationError({
                    "items": f"Not enough stock for {product.title}. Only {product.stock} left."
                })
                
            # Deduct stock
            product.stock -= quantity
            product.save()

            # Add to grand total
            grand_total += product_price_after_discount+product_delivery_cost

        validated_data.pop('total_amount', None)  # Remove total_amount if it was provided in the request, since we calculate it here

        # 3. Create the Parent Order
        order = Order.objects.create(
            buyer=self.context['request'].user,
            seller=seller,
            total_amount=grand_total,
            **validated_data
        )

        # 4. Create the Child OrderItems
        for item in items_data:
            product = item['product']
            quantity = item['quantity']
            product_price_after_discount = item['product_price_after_discount']
            product_delivery_cost = item['product_delivery_cost']
            

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                product_price_after_discount=product_price_after_discount,
                product_delivery_cost=product_delivery_cost
                
            )
        OrderStatusHistory.objects.create(order=order, status=order.status)  # Log initial status

        return order
        
# Keep your OrderStatusUpdateSerializer and OrderCancelSerializer as they were.
class OrderStatusUpdateSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Order
        fields = ('status',)

    def update(self, instance, validated_data):
        old_status = instance.status
        new_status = validated_data.get('status')

        print(f"\n--- DEBUG STATUS UPDATE ---")
        print(f"Old Status: {old_status} | New Status: {new_status}")

        # If same status → do nothing
        if old_status == new_status:
            print("❌ Status is the same! Skipping notification.")
            return instance

        # Update order status
        instance.status = new_status
        instance.save()

        # ✅ Add history record
        OrderStatusHistory.objects.create(
            order=instance,
            status=new_status
        )
        
        print("✅ Status updated in DB. Triggering notification function...")
        status_display = dict(Order.STATUS_CHOICES).get(new_status, new_status)
        send_order_status_notification(user=instance.buyer, order=instance, status_display=status_display)

        return instance

class OrderCancelSerializer(serializers.Serializer):
    cancel_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

class ProductOfferSerializer(serializers.ModelSerializer):
    offer_product_image = serializers.SerializerMethodField(read_only=True)
    product=ProductSerializer(read_only=True)
    
    class Meta:
        model = ProductOffer
        fields = '__all__'
        read_only_fields = ['seller', 'product', 'created_at']
    def get_offer_product_image(self, obj): 
        request = self.context.get('request')  
        first_image = obj.product.images.first()
        if first_image and first_image.image:
            # build absolute URL
            return request.build_absolute_uri(first_image.image.url)
        return None



class CartItemSerializer(serializers.ModelSerializer):
    cart_id = serializers.IntegerField(source='cart.id', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)
    product_weight = serializers.CharField(source='product.weight', read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)
    product_seller = SellerProfileSerializer(source='product.seller', read_only=True)
    product_price = serializers.DecimalField(source='product.discounted_price', max_digits=10, decimal_places=2, read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    product_image = serializers.SerializerMethodField(read_only=True)
    delivery_cost = serializers.DecimalField(source='product.delivery_cost', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'cart_id', 'product', 'product_title', 'product_weight', 'product_unit', 'product_seller', 'product_price', 'quantity', 'total_price', 'product_image', 'delivery_cost']
    def get_product_image(self, obj):
        request = self.context.get('request')  
        first_image = obj.product.images.first()
        if first_image and first_image.image:
            # build absolute URL
            return request.build_absolute_uri(first_image.image.url)
        return None

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, data):
        product = data.get('product')  # ✅ Use .get() instead of direct access
        
        # Only validate stock if product is being set/changed
        if product is not None:
            quantity = data.get('quantity', 1)
            if quantity > product.stock:
                raise serializers.ValidationError(
                    f"Only {product.stock} units available in stock."
                )
        
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        product = validated_data['product']
        quantity = validated_data.get('quantity', 1)

        # Ensure the user has only one cart
        cart, created = Cart.objects.get_or_create(user=user)

        # Check if product already exists in cart
        existing_item = CartItem.objects.filter(cart=cart, product=product).first()
        if existing_item:
            new_quantity = existing_item.quantity + quantity

            # Re-check stock for updated quantity
            if new_quantity > product.stock:
                raise serializers.ValidationError(
                    f"Cannot add {quantity} units. Only {product.stock - existing_item.quantity} more available."
                )

            existing_item.quantity = new_quantity
            existing_item.save()
            return existing_item
        else:
            return CartItem.objects.create(cart=cart, **validated_data)

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    class Meta:
        model = Cart
        fields = ['id', 'user', 'created_at', 'items', 'total_price']
        read_only_fields = '__all__'




class SellerSiteOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True) 
    order_status_history = serializers.SerializerMethodField(read_only=True)
    
    # 👇 This will show the buyer's details (name, photo, etc.)
    buyer_details = UserDetailSerializer(source='buyer', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'items', 'delivery_location', 'payment_type', 
            'tracking_number', 'total_amount', 'status', 'created_at', 
            'order_status_history', 'buyer_details'
        ]
    
    def get_order_status_history(self, obj):
        history = OrderStatusHistory.objects.filter(order=obj).order_by('timestamp')
        return OrderStatusHistorySerializer(history, many=True).data

