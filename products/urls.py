from rest_framework.routers import DefaultRouter, path
from rest_framework_nested.routers import NestedDefaultRouter
from .views import CancelOrderView, CartDeleteAPIView, CartItemViewSet, CategoryViewSet, GetOrderAPIView, ProductGetByCategoryView, ProductImageViewSet, ProductOfferListAPIView, ProductReviewViewSet, ProductViewSet, PlaceOrderAPIView, SellerOrderListView, SellerOrderStatusUpdateView

router = DefaultRouter()
router.register('categories', CategoryViewSet)
router.register('products', ProductViewSet)
router.register('product-images', ProductImageViewSet)
router.register(r'cart-items', CartItemViewSet, basename='cartitem')


products_router = NestedDefaultRouter(router, 'products', lookup='product')
products_router.register('reviews', ProductReviewViewSet, basename='product-reviews')



urlpatterns = router.urls + products_router.urls + [
    path('cart/delete/<int:id>/', CartDeleteAPIView.as_view(), name='delete-cart'),
    path('place-order/', PlaceOrderAPIView.as_view(), name='place-order'),
    path('orders/', GetOrderAPIView.as_view(), name='get-orders'),
    path('orders/<int:pk>/cancel/', CancelOrderView.as_view(), name='order-cancel'),
    path('product-offers/', ProductOfferListAPIView.as_view(), name='product-offers-list'),
    path('products/by-category/<slug:category_slug>/', ProductGetByCategoryView.as_view(), name='product-get-by-category'),
    path('seller/orders/', SellerOrderListView.as_view(), name='seller-orders-list'),
    path('seller/orders/<int:pk>/status/', SellerOrderStatusUpdateView.as_view(), name='seller-order-status-update'),
]