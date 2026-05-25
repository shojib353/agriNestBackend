from rest_framework.routers import DefaultRouter
from django.urls import path, include
from . import views

router = DefaultRouter()
# Add this line to your existing router registrations
router.register('driver-orders', views.DriverOrderViewSet, basename='driver-orders')

urlpatterns = router.urls+[
    path('drivers/', views.DriverListAPIView.as_view(), name='driver-list'),# /drivers/?driver_type=string for filtering by driver type

]