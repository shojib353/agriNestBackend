from django.urls import include, path
from rest_framework.routers import DefaultRouter


from driver_order.views import DriverOrderViewSet
from .views import CustomTokenRefreshView, DriverProfileViewSet, FCMTokenUpdateView, LogoutView, RegisterView, LoginView, ResetPasswordView, SellerProfileViewSet, SendOTPView, UserLocationUpdateView, VerifyOTPForRegistrationView, VerifyOTPView,UserProfileView
router = DefaultRouter()
router.register(r'sellers', SellerProfileViewSet, basename='seller')
router.register(r'drivers', DriverProfileViewSet, basename='driver')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', UserProfileView.as_view(), name='profile'),

    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('verify-otp-registration/', VerifyOTPForRegistrationView.as_view(), name='verify-otp-registration'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('fcm-token/', FCMTokenUpdateView.as_view(), name='update_fcm_token'),
    path('update-location/', UserLocationUpdateView.as_view(), name='update-user-location'),
    path('', include(router.urls)),

]