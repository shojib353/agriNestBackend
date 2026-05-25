from rest_framework import generics, filters 
from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import DriverOrder
from .serializers import DriverOrderSerializer
from agriAuthentication.serializers import DriverProfileSerializer
from agriAuthentication.models import DriverProfile

class DriverOrderViewSet(viewsets.ModelViewSet):
    serializer_class = DriverOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # If the user is a driver, show jobs they requested PLUS jobs assigned to them
        if hasattr(user, 'driver_profile'):
            return DriverOrder.objects.filter(
                Q(buyer=user) | Q(driver=user.driver_profile)
            )
            
        # If just a regular buyer, only show their requests
        return DriverOrder.objects.filter(buyer=user)

    def perform_create(self, serializer):
        # Automatically attach the logged-in user as the buyer
        serializer.save(buyer=self.request.user)

    # --- CUSTOM STATUS ACTIONS ---

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        order = self.get_object()
        
        # Security check: Only the assigned driver can accept
        if not hasattr(request.user, 'driver_profile') or order.driver != request.user.driver_profile:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
        if order.status != DriverOrder.JobStatus.REQUESTED:
            return Response({"detail": "Job is no longer pending."}, status=status.HTTP_400_BAD_REQUEST)
            
        order.status = DriverOrder.JobStatus.ACCEPTED
        order.save()
        return Response({"status": "Job accepted", "order_id": order.id})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        order = self.get_object()
        
        if not hasattr(request.user, 'driver_profile') or order.driver != request.user.driver_profile:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
        if order.status != DriverOrder.JobStatus.ACCEPTED:
            return Response({"detail": "Job must be accepted before it can be completed."}, status=status.HTTP_400_BAD_REQUEST)

        order.status = DriverOrder.JobStatus.COMPLETED
        order.save()
        return Response({"status": "Job completed", "order_id": order.id})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        user = request.user

        # If the buyer is cancelling
        if order.buyer == user:
            order.status = DriverOrder.JobStatus.CANCELLED_BY_BUYER
        # If the driver is cancelling
        elif hasattr(user, 'driver_profile') and order.driver == user.driver_profile:
            order.status = DriverOrder.JobStatus.CANCELLED_BY_DRIVER
        else:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        order.save()
        return Response({"status": f"Job cancelled by {user.role}", "order_id": order.id})
    
class DriverListAPIView(generics.ListAPIView):
    """
    API endpoint that allows listing all drivers.
    Can be filtered by driver_type using query parameters.
    """
    serializer_class = DriverProfileSerializer
    filter_backends = [filters.SearchFilter]

    search_fields = ['user__full_name', 'driver_type', 'base_location']

    def get_queryset(self):
        # Base queryset: only approved drivers, optimize with select_related
        queryset = DriverProfile.objects.select_related('user').filter(status='approved')

        # Keep your existing exact category filter
        driver_type = self.request.query_params.get('driver_type', None)
        if driver_type is not None:
            queryset = queryset.filter(driver_type=driver_type)

        return queryset
