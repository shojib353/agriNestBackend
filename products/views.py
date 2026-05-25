from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status,generics,serializers
from .models import Cart, CartItem, Category, Order,Product,ProductImage, ProductReview,ProductOffer,OrderStatusHistory
from .serializers import CartItemSerializer, CartSerializer, CategorySerializer, OrderCancelSerializer, OrderSerializer, OrderStatusUpdateSerializer, ProductOfferSerializer, ProductReviewSerializer,ProductSerializer,ProductImageSerializer, SellerSiteOrderSerializer
from .permissions import IsAdminRoleUser, IsReviewOwnerOrReadOnly, IsSellerOrReadOnly
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from rest_framework import filters



class CategoryViewSet(ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRoleUser]
    lookup_field = 'slug'

   



class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsSellerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    filter_backends = [filters.SearchFilter]

    search_fields = ['title', 'description', 'category__name']

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user.seller_profile)

    def get_serializer_context(self):
        return {'request': self.request}  
    
    @action(detail=False, methods=['get'], url_path='popular')
    def popular_products(self, request):
        """
        Endpoint: GET /api/products/popular/
        Returns products marked as popular (is_popular=True), paginated.
        """
        # 1. Filter the queryset by the boolean field.
        # Note: We add .order_by('-created_at') because DRF pagination 
        # requires an ordered queryset to work correctly and prevent duplicates.
        popular_qs = self.get_queryset().filter(
            is_popular=True, 
            is_active=True  # Good practice to also ensure it's active
        ).order_by('-created_at')

        # 2. Apply the viewset's built-in pagination
        page = self.paginate_queryset(popular_qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # 3. Fallback if pagination is turned off
        serializer = self.get_serializer(popular_qs, many=True)
        return Response(serializer.data)

class ProductGetByCategoryView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        category_slug = self.kwargs.get('category_slug')
        return Product.objects.filter(category__slug=category_slug, is_active=True).order_by('-created_at')
    
    def get_serializer_context(self):
        return {'request': self.request}   # 🔥 IMPORTANT

# Optional: Separate Image ViewSet if you want to upload images independently
class ProductImageViewSet(ModelViewSet):

    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsSellerOrReadOnly]

    def perform_create(self, serializer):
        # Automatically link the product if provided in request data
        serializer.save()



class ProductReviewViewSet(ModelViewSet):
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsReviewOwnerOrReadOnly]

    def get_queryset(self):
        # Use .get() so it doesn't crash if the key is missing
        product_pk = self.kwargs.get('product_pk')
        
        # If it's a real request with an ID, filter normally
        if product_pk:
            return ProductReview.objects.filter(product_id=product_pk)
            
        # If it's a schema generator, safely return an empty queryset
        return ProductReview.objects.none() 

    def perform_create(self, serializer):
        # Also use .get() here just to be completely safe
        serializer.save(
            user=self.request.user,
            product_id=self.kwargs.get('product_pk')
        )


class PlaceOrderAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            order = serializer.save()
            return Response(
                {"message": "Order placed successfully", "order_id": order.id},
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GetOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        orders = Order.objects.filter(buyer=user).order_by('-created_at')

        serializer = OrderSerializer(orders, many=True, context={'request': request})
        return Response(serializer.data)
    

class CancelOrderView(generics.GenericAPIView):
    serializer_class = OrderCancelSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        # 1. Fetch the order
        order = get_object_or_404(Order, pk=pk)

        # 2. Security Check: Only the Buyer or the Seller of this specific order can cancel it
        if request.user != order.buyer and request.user != order.seller:
            return Response(
                {"detail": "You do not have permission to cancel this order."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Status Check: Prevent canceling orders that are already done
        # (Adjust the strings 'Cancelled' and 'Delivered' to match your actual model choices)
        if order.status in ['Cancelled', 'Delivered', 'Shipped']:
            return Response(
                {"detail": f"Order cannot be cancelled because it is currently marked as {order.status}."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Validate the cancel reason from the request
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_reason = serializer.validated_data.get('cancel_reason', '')

        # 5. RESTORE INVENTORY: Loop through the items and give the stock back to the seller
        for item in order.items.all():
            product = item.product
            product.stock += item.quantity
            product.save()

        # 6. Update the Order
        order.status = 'cancelled'
        
        # Optional: If you added a 'cancel_reason' text field to your Order model, save it here:
        order.cancel_reason = cancel_reason 

        
        order.save()
        # 7. ✅ UPDATE ORDER HISTORY STATUS
        OrderStatusHistory.objects.create(
            order=order, 
            status='cancelled'
        )

        return Response({"detail": "Order has been successfully cancelled and stock restored."}, status=status.HTTP_200_OK)
    
from rest_framework.generics import ListAPIView

class ProductOfferListAPIView(ListAPIView):
    queryset = ProductOffer.objects.all()
    serializer_class = ProductOfferSerializer




class CartItemViewSet(ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user)

    def perform_destroy(self, instance):
        cart = instance.cart
        instance.delete()

        # Auto-delete cart if empty
        if cart.items.count() == 0:
            cart.delete()
class CartDeleteAPIView(generics.DestroyAPIView):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    lookup_field = 'id'


class SellerOrderListView(generics.ListAPIView):
    """
    Returns all incoming orders for the logged-in seller, including buyer details.
    """
    serializer_class = SellerSiteOrderSerializer # 👈 UPDATE THIS LINE
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'seller_profile'):
            return Order.objects.filter(seller=user.seller_profile).order_by('-created_at')
        return Order.objects.none()


class SellerOrderStatusUpdateView(generics.UpdateAPIView):
    """
    Allows a seller to update the status of their orders.
    """
    serializer_class = OrderStatusUpdateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        # Restrict the queryset so sellers can only update their own orders
        if hasattr(user, 'seller_profile'):
            return Order.objects.filter(seller=user.seller_profile)
        return Order.objects.none()