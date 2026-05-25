from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, SellerProfile, DriverProfile, ApprovalStatus

# -----------------------------
# Custom User Admin
# -----------------------------
class UserAdmin(BaseUserAdmin):
    list_display = ('id','email', 'full_name', 'role', 'is_staff', 'is_active','is_verified', 'location', 'is_suspended', 'warning_count')
    list_filter  = ('role', 'is_staff', 'is_active', 'is_suspended')
    search_fields = ('email', 'full_name', 'phone')
    ordering = ('email',)
    list_editable = ('is_active', 'is_suspended', 'is_verified')  # Allow quick toggling of these fields
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name', 'phone', 'photo', 'location', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Other Info', {'fields': ('is_suspended', 'warning_count', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2', 'role', 'is_staff', 'is_superuser'),
        }),
    )

# -----------------------------
# Seller Profile Admin
# -----------------------------
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'user','location',  'status', 'escrow_balance', 'total_earnings', 'approved_date')
    list_filter  = ('status',)
    search_fields = ('shop_name', 'user__email', 'user__full_name')

# -----------------------------
# Driver Profile Admin
# -----------------------------
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'driver_type', 'base_location', 'rate_per_job', 'status', 'is_available', 'approved_date')
    list_filter  = ('driver_type', 'status', 'is_available')
    search_fields = ('user__email', 'user__full_name', 'base_location')

# -----------------------------
# Register Models
# -----------------------------
admin.site.register(User, UserAdmin)
admin.site.register(SellerProfile, SellerProfileAdmin)
admin.site.register(DriverProfile, DriverProfileAdmin)