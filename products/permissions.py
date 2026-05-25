from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsSellerOrReadOnly(BasePermission):
    """
    Custom permission:
    - Sellers can create, update, delete their own products.
    - Others can only read.
    """

    def has_permission(self, request, view):
# 1. Anyone can read
        if request.method in SAFE_METHODS:
            return True
            
        # 2. Only authenticated users can get past this point
        if not (request.user and request.user.is_authenticated):
            return False
            
        # 3. Check if the user is a seller AND their status is approved
        # (This prevents unapproved sellers from creating new products)
        if hasattr(request.user, 'seller_profile'):
            return request.user.seller_profile.status == 'approved'
            
        return False

    def has_object_permission(self, request, view, obj):
        # Anyone can read
        if request.method in SAFE_METHODS:
            return True
        # If the object is a ProductImage, check the related product's seller
        if hasattr(obj, 'product'):
            return obj.product.seller.user == request.user
        # Only the seller who owns the product can modify
        return obj.seller.user == request.user
    

class IsReviewOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.user == request.user

class IsAdminRoleUser(BasePermission):
    """
    Custom permission:
    - Allow GET for everyone
    - Only allow POST/PUT/PATCH/DELETE for users with role='admin'
    """
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return request.user.is_authenticated and getattr(request.user, 'role', None) == 'admin'