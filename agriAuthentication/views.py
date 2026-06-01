from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from rest_framework import generics, status

from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.conf import settings
from django.core.mail import send_mail
from firebase_admin import auth

from rest_framework import generics, status
from rest_framework import permissions
from rest_framework.decorators import APIView, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.viewsets import ModelViewSet

from .models import ApprovalStatus, DriverProfile, FCMToken, SellerProfile,OTP
from .serializers import DriverProfileSerializer, LogoutSerializer, SellerProfileSerializer, UserLocationUpdateSerializer, UserProfileSerializer, UserRegistrationSerializer, UserLoginSerializer, OTPRequestSerializer, OTPVerifySerializer, ResetPasswordSerializer,FCMTokenSerializer
from django.contrib.auth.models import update_last_login
from rest_framework.parsers import MultiPartParser, FormParser

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from asgiref.sync import sync_to_async

User = get_user_model()

# Helper to generate JWT tokens
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class CustomTokenRefreshView(APIView):
    """
    Accepts a refresh token and returns a new access token.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token = RefreshToken(refresh_token)
            access_token = str(token.access_token)
            return Response({"access": access_token}, status=status.HTTP_200_OK)

        except TokenError as e:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED
            )

class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            # Get the refresh token from the request body
            refresh_token = request.data.get("refresh")
            
            if not refresh_token:
                return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

            # Blacklist the token
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"detail": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)
            
        except Exception as e:
            return Response({"detail": "Invalid token or already logged out."}, status=status.HTTP_400_BAD_REQUEST)
# Registration API
class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if existing_user.is_verified:
                return Response(
                    {"error": "User already exists and is verified."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                # ❗ Delete unverified user
                existing_user.delete()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if user.is_verified:
            token = get_tokens_for_user(user)
            update_last_login(None, user)

            return Response(
                {'user': serializer.data, 'token': token},
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {
                    'user': serializer.data,
                    'message': 'Registration successful. Please verify your account.'
                },
                status=status.HTTP_201_CREATED
            )



# Login API
class LoginView(generics.GenericAPIView):
    serializer_class = UserLoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        if not user.is_verified:
            user.delete()
            return Response(
                {"error": "User is not verified. Account deleted."},
                status=status.HTTP_403_FORBIDDEN
            )
        token = get_tokens_for_user(user)
        update_last_login(None, user)
        return Response({'user': {'email': user.email, 'full_name': user.full_name, 'role': user.role,'location': user.location}, 'token': token})
    

    # Send OTP
# class SendOTPView(generics.GenericAPIView):

#     ten_minutes_ago = timezone.now() - timedelta(minutes=10)
#     OTP.objects.filter(created_at__lt=ten_minutes_ago).delete()
#     serializer_class = OTPRequestSerializer
#     permission_classes = [AllowAny]

#     def post(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         otp = serializer.save()

#         # Send OTP via email
#         send_mail(
#             subject="Your OTP Code",
#             message=f"Your OTP is {otp.code}. It is valid for 10 minutes.",
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[otp.user.email],
#         )

#         return Response({'detail': 'OTP sent to email'}, status=status.HTTP_200_OK)

@sync_to_async
def send_otp_email_async(subject, message, from_email, recipient_list):
    send_mail(
        subject,
        message,
        from_email,
        recipient_list,
        fail_silently=False,
    )

class SendOTPView(generics.GenericAPIView):
    serializer_class = OTPRequestSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # Clean up old OTPs
        ten_minutes_ago = timezone.now() - timedelta(minutes=10)
        OTP.objects.filter(created_at__lt=ten_minutes_ago).delete()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.save()

        # 🔥 ASYNC FIX: Send OTP via email in a background task
        asyncio.create_task(
            send_otp_email_async(
                subject="Your OTP Code",
                message=f"Your OTP is {otp.code}. It is valid for 10 minutes.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[otp.user.email],
            )
        )

        return Response({'detail': 'OTP sent to email'}, status=status.HTTP_200_OK)

# class SendOTPView(generics.GenericAPIView):
#     serializer_class = OTPRequestSerializer
#     permission_classes = [AllowAny]

#     def post(self, request, *args, **kwargs):
#         # ✅ MOVED HERE: Now it only runs when someone requests an OTP
#         ten_minutes_ago = timezone.now() - timedelta(minutes=10)
#         OTP.objects.filter(created_at__lt=ten_minutes_ago).delete()

#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         otp = serializer.save()

#         # Send OTP via email
#         send_mail(
#             subject="Your OTP Code",
#             message=f"Your OTP is {otp.code}. It is valid for 10 minutes.",
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[otp.user.email],
#         )

#         return Response({'detail': 'OTP sent to email'}, status=status.HTTP_200_OK)
    

# Note: OTP verification after registration
class VerifyOTPForRegistrationView(generics.GenericAPIView):
    serializer_class = OTPVerifySerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        code = serializer.validated_data['otp']

        try:
            otp = OTP.objects.filter(
                user__email=email,
                code=code,
                is_used=False
            ).latest('created_at')
        except OTP.DoesNotExist:
            return Response(
                {'detail': 'Invalid OTP'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not otp.is_valid():
            return Response(
                {'detail': 'OTP expired'},
                status=status.HTTP_400_BAD_REQUEST
            )

        otp.is_used = True
        otp.save()

        user = otp.user

        # 🔥 Prevent re-verification
        if user.is_verified:
            return Response(
                {"detail": "User already verified"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.is_verified = True
        user.save()

        token = get_tokens_for_user(user)
        update_last_login(None, user)

        return Response(
            {
                'user': {
                    'email': user.email,
                    'full_name': user.full_name,
                    'role': user.role
                    
                },
                'token': token
            },
            status=status.HTTP_200_OK
        )

# Verify OTP
class VerifyOTPView(generics.GenericAPIView):
    serializer_class = OTPVerifySerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        code = serializer.validated_data['otp']

        try:
            otp = OTP.objects.filter(user__email=email, code=code, is_used=False).latest('created_at')
        except OTP.DoesNotExist:
            return Response({'detail': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)

        if not otp.is_valid():
            return Response({'detail': 'OTP expired'}, status=status.HTTP_400_BAD_REQUEST)

        otp.is_used = True
        otp.save()
        return Response({'detail': 'OTP verified'}, status=status.HTTP_200_OK)


# Reset Password (Step 3)
class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Notice: We do NOT need the OTP code here anymore!
        email = serializer.validated_data['email']
        new_password = serializer.validated_data['new_password']

        try:
            # Look for an OTP for this email that is VERIFIED but NOT USED
            otp = OTP.objects.filter(user__email=email, is_used=True).latest('created_at')
        except OTP.DoesNotExist:
            return Response({'detail': 'Session expired or OTP not verified.'}, status=status.HTTP_400_BAD_REQUEST)

        # Double-check that they didn't wait too long after verifying
        time_difference = (timezone.now() - otp.created_at).total_seconds()
        if time_difference > 600:
            otp.delete() # Clean up the expired OTP
            return Response({'detail': 'OTP session expired. Please start over.'}, status=status.HTTP_400_BAD_REQUEST)


        # Change the user's password
        user = otp.user
        user.set_password(new_password)
        user.save()
        otp.delete()  # Clean up OTP after successful password reset
        return Response({'detail': 'successful'}, status=status.HTTP_200_OK)
    

# Permission: Only owner can view/edit, admin can approve
class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user == obj.user or request.user.role == 'admin'


class SellerProfileViewSet(ModelViewSet):
    queryset = SellerProfile.objects.all()
    serializer_class = SellerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        user = self.request.user
        
        # 1. Safely handle unauthenticated users (like Swagger schema generation)
        if not user.is_authenticated:
            return SellerProfile.objects.none()
             
        # 3. Handle regular authenticated users
        return SellerProfile.objects.all()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        profile = self.get_object()
        profile.status = ApprovalStatus.APPROVED
        profile.save()
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        profile = self.get_object()
        profile.status = ApprovalStatus.REJECTED
        profile.save()
        return Response({'status': 'rejected'})


class DriverProfileViewSet(ModelViewSet):
    queryset = DriverProfile.objects.all()
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        user = self.request.user
        
        # 1. Safely handle unauthenticated users (like Swagger schema generation)
        if not user.is_authenticated:
            return DriverProfile.objects.none()
            
        # 2. Handle Admin users
        if getattr(user, 'role', None) == 'admin':
            return DriverProfile.objects.all()
            
        # 3. Handle regular authenticated users
        return DriverProfile.objects.filter(user=user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        profile = self.get_object()
        profile.status = ApprovalStatus.APPROVED
        profile.save()
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        profile = self.get_object()
        profile.status = ApprovalStatus.REJECTED
        profile.save()
        return Response({'status': 'rejected'})

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieves or updates the currently logged-in user's profile.
    Dynamically fetches buyer, seller, or driver details.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self):
        # Always return the currently authenticated user
        return self.request.user

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def save_fcm_token(request):
#     token = request.data.get('token')
#     if not token:
#         return Response({'error': 'Token is required'}, status=400)
    
#     # Create or update the token for the authenticated user
#     FCMToken.objects.update_or_create(
#         user=request.user,
#         defaults={'token': token}
#     )
#     return Response({'message': 'Token saved successfully'})

class FCMTokenUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FCMTokenSerializer(data=request.data)
        
        if serializer.is_valid():
            token = serializer.validated_data.get('token')
            
            # Create or update the token linked to the currently logged-in user
            fcm_token, created = FCMToken.objects.update_or_create(
                user=request.user,
                defaults={'token': token}
            )
            
            return Response(
                {
                    "message": "Token saved successfully", 
                    "token": fcm_token.token
                }, 
                status=status.HTTP_200_OK
            )
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class UserLocationUpdateView(generics.UpdateAPIView):
    serializer_class = UserLocationUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Securely return the user making the request
        return self.request.user



class GoogleSignInView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        id_token = request.data.get('id_token')

        if not id_token:
            return Response({'error': 'ID token is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Verify the token with Firebase
            decoded_token = auth.verify_id_token(id_token)
            email = decoded_token.get('email')
            full_name = decoded_token.get('name', 'Google User')

            if not email:
                return Response({'error': 'Google token did not contain an email'}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Get or Create the User
            user, created = User.objects.get_or_create(email=email, defaults={
                'full_name': full_name,
                'is_verified': True, # Google users are already verified
                'role': User.Role.BUYER # Default role
            })

            if created:
                user.set_unusable_password() # They don't have a standard password
                user.save()

            # 3. Issue your standard JWT tokens
            token = get_tokens_for_user(user)
            update_last_login(None, user)

            return Response({
                'user': {
                    'email': user.email,
                    'full_name': user.full_name,
                    'role': user.role,
                    'location': user.location
                },
                'token': token
            }, status=status.HTTP_200_OK)

        except auth.InvalidIdTokenError:
            return Response({'error': 'Invalid or expired Google token'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)