from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import FCMToken, User, SellerProfile, DriverProfile
from .models import OTP
import random

# User Registration Serializer
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['email', 'full_name', 'password', 'phone', 'role', 'location']

    def create(self, validated_data):
        role = validated_data.get('role')
        user = User.objects.create_user(**validated_data)

        # Create profile based on role
        if role == User.Role.SELLER:
            SellerProfile.objects.create(user=user, shop_name=f"{user.full_name}'s Shop", location=user.location)
        elif role == User.Role.DRIVER:
            DriverProfile.objects.create(user=user, driver_type='truck', base_location=user.location)
        
        return user

# User Login Serializer
class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(email=email, password=password)
            if not user:
                raise serializers.ValidationError('Invalid email or password')
            if not user.is_active:
                raise serializers.ValidationError('User is inactive')
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Email and password required')
        
#logout serializer
class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        help_text="The refresh token obtained during login."
    )

    default_error_messages = {
        'bad_token': 'Token is invalid or already logged out.'
    }

    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        try:
            # Attempt to blacklist the token
            token = RefreshToken(self.token)
            token.blacklist()
        except TokenError:
            # Raise a clean validation error if the token is already blacklisted or invalid
            self.fail('bad_token')





class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def create(self, validated_data):
        email = validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")

        # Generate 6-digit OTP
        otp_code = str(random.randint(100000, 999999))
        otp = OTP.objects.create(user=user, code=otp_code)
        return otp

class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField(min_length=6, write_only=True)
    new_password_confirm = serializers.CharField(min_length=6, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("The two password fields didn't match.")
        return attrs



class SellerProfileSerializer(serializers.ModelSerializer):
    # Read-only fields
    seller_service = serializers.SerializerMethodField()
    seller_userID = serializers.IntegerField(source='user.id', read_only=True)  
    phone = serializers.CharField(source='user.phone', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = SellerProfile
        fields = [
            'id', 'seller_userID', 'user_email', 'user_full_name', 'shop_name', 'phone','shop_image',
            'shop_description', 'location', 'status',
            'seller_service'
        ]
        read_only_fields = [ 'user','status', 'seller_service','phone',]
    def get_seller_service(self, obj):
            # Empty order_by() strips default ordering that causes duplicates
            categories = obj.products.order_by().values_list('category__name', flat=True).distinct()
            return list(categories)
    def get_phone(self, obj):
        return obj.user.phone
    


class DriverProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    

    class Meta:
        model = DriverProfile
        fields = [
            'id', 'user', 'user_email', 'user_full_name', 'driver_type', 'photo',
            'base_location', 'rate_per_job', 'status', 'is_available', 'approved_date'
        ]
        read_only_fields = ['user','status', 'is_available', 'approved_date']


class UserProfileSerializer(serializers.ModelSerializer):
    # 1. Explicitly declare the Seller write-only fields
    shop_name = serializers.CharField(write_only=True, required=False)
    shop_description = serializers.CharField(write_only=True, required=False)
    shop_image = serializers.ImageField(write_only=True, required=False)

    # 2. Explicitly declare the Driver write-only fields
    driver_type = serializers.CharField(write_only=True, required=False)
    base_location = serializers.CharField(write_only=True, required=False)
    rate_per_job = serializers.DecimalField(max_digits=10, decimal_places=2, write_only=True, required=False)

    # 3. Declare dynamic read-only fields for the details
    seller_details = serializers.SerializerMethodField()
    driver_details = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'photo', 'email', 'full_name', 'phone', 'role', 'location',
            'shop_name', 'shop_description', 'shop_image', 
            'driver_type', 'base_location', 'rate_per_job',
            'seller_details', 'driver_details'
        ]
        read_only_fields = ['email', 'role']

    # --- READ LOGIC (Replaces to_representation) ---
    
    def get_seller_details(self, instance):
        if instance.role == User.Role.SELLER:
            try:
                seller_profile = SellerProfile.objects.get(user=instance)
                return SellerProfileSerializer(seller_profile, context=self.context).data
            except SellerProfile.DoesNotExist:
                return None
        return None # Returns null for Buyers and Drivers

    def get_driver_details(self, instance):
        if instance.role == User.Role.DRIVER:
            try:
                driver_profile = DriverProfile.objects.get(user=instance)
                return DriverProfileSerializer(driver_profile, context=self.context).data
            except DriverProfile.DoesNotExist:
                return None
        return None # Returns null for Buyers and Sellers

    # --- WRITE LOGIC ---

    def update(self, instance, validated_data):
        # 1. Pop the dynamically added fields out of the validated_data BEFORE updating the User
        shop_name = validated_data.pop('shop_name', None)
        shop_description = validated_data.pop('shop_description', None)
        shop_image = validated_data.pop('shop_image', None)
        
        driver_type = validated_data.pop('driver_type', None)
        base_location = validated_data.pop('base_location', None)
        driver_rate_per_job = validated_data.pop('rate_per_job', None)

        # 2. Update the base User instance
        instance = super().update(instance, validated_data)

        # 3. Update the Seller Profile
        if instance.role == User.Role.SELLER:
            try:
                seller_profile = SellerProfile.objects.get(user=instance)
                
                if shop_name:
                    seller_profile.shop_name = shop_name
                if shop_description:
                    seller_profile.shop_description = shop_description
                if shop_image:
                    seller_profile.shop_image = shop_image
                    
                seller_profile.save()
            except SellerProfile.DoesNotExist:
                pass

        # 4. Update the Driver Profile
        elif instance.role == User.Role.DRIVER:
            try:
                driver_profile = DriverProfile.objects.get(user=instance)
                
                if driver_type:
                    driver_profile.driver_type = driver_type
                if base_location:
                    driver_profile.base_location = base_location
                if driver_rate_per_job:
                    driver_profile.rate_per_job = driver_rate_per_job
                driver_profile.save()
            except DriverProfile.DoesNotExist:
                pass
        
        return instance
    


class FCMTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMToken
        fields = ['token', 'updated_at']
        read_only_fields = ['updated_at']


class UserLocationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['location']