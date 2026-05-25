from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        BUYER  = 'buyer',  'Buyer'
        SELLER = 'seller', 'Seller'
        DRIVER = 'driver', 'Driver'
        ADMIN  = 'admin',  'Admin'

    email        = models.EmailField(unique=True)
    phone        = models.CharField(max_length=20, blank=True, null=True, unique=True)
    full_name    = models.CharField(max_length=150)
    photo        = models.ImageField(upload_to='profiles/', blank=True, null=True)
    role         = models.CharField(max_length=10, choices=Role.choices, default=Role.BUYER)
    location     = models.CharField(max_length=255,null=True, blank=True)

    is_active    = models.BooleanField(default=True)
    is_staff     = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    warning_count = models.PositiveIntegerField(default=0)
    date_joined  = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD  = 'email'

    def __str__(self):
        return f'{self.full_name} ({self.role})'


# Shared Status for Profiles (Replaces RoleApplication)
class ApprovalStatus(models.TextChoices):
    PENDING  = 'pending',  'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class SellerProfile(models.Model):
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')
    shop_name        = models.CharField(max_length=200)
    shop_image       = models.ImageField(upload_to='shop_images/', blank=True, null=True)
    shop_description = models.TextField(blank=True)
    location         = models.CharField(max_length=255)
    
    # Application / Verification Status
    status           = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    
    # Escrow
    escrow_balance   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earnings   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approved_date = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Automatically set the date when approved
        if self.status == ApprovalStatus.APPROVED and self.approved_date is None:
            self.approved_date = timezone.now()
            # Update user role to SELLER
            self.user.role = User.Role.SELLER
            self.user.save(update_fields=['role'])
        elif self.status != ApprovalStatus.APPROVED:
            # Clear approved_date
            self.approved_date = None
            # Revert user role to BUYER if not admin
            if self.user.role != User.Role.ADMIN:
                self.user.role = User.Role.BUYER
                self.user.save(update_fields=['role'])
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.shop_name

class DriverProfile(models.Model):
    class DriverType(models.TextChoices):
        TRUCK     = 'truck',   'Truck'
        TRACTOR   = 'tractor', 'Tractor'
        PICKUP    = 'pickup',       'Pickup Van'
        MINI_TRUCK= 'mini_truck',   'Mini Truck'

    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    driver_type     = models.CharField(max_length=20, choices=DriverType.choices)
    base_location   = models.CharField(max_length=255)
    
    # Pricing
    rate_per_job    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    photo           = models.ImageField(upload_to='driver_profiles/', blank=True, null=True)
    
    # Application / Verification Status
    status          = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    is_available    = models.BooleanField(default=True)
    approved_date = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Automatically set the date when approved
        if self.status == ApprovalStatus.APPROVED and self.approved_date is None:
            self.approved_date = timezone.now()
            # Update user role to DRIVER
            self.user.role = User.Role.DRIVER
            self.user.save(update_fields=['role'])
        # Clear the date if an admin revokes their approval
        elif self.status != ApprovalStatus.APPROVED:
            self.approved_date = None
            # Revert user role to BUYER if not admin
            if self.user.role != User.Role.ADMIN:
                self.user.role = User.Role.BUYER
                self.user.save(update_fields=['role'])

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.full_name} - {self.driver_type}'
    

class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        """Check if OTP is valid (not used and within 10 minutes)"""
        return not self.is_used and (timezone.now() - self.created_at).total_seconds() < 600

    def __str__(self):
        return f"{self.user.email} - {self.code}"
    
class FCMToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='fcm_token')
    token = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Token"

    