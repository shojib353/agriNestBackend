from rest_framework import serializers, generics


from .models import DriverOrder

class DriverOrderSerializer(serializers.ModelSerializer):
    # Optional: Display readable names alongside IDs
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    driver_name = serializers.CharField(source='driver.user.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = DriverOrder
        fields = [
            'id', 'buyer', 'buyer_name', 'driver', 'driver_name', 
            'pickup_location', 'dropoff_location', 'job_date', 
            'job_description', 'agreed_price', 'status', 'status_display',
            'created_at', 'updated_at'
        ]
        # Prevent users from altering these fields manually
        read_only_fields = ['buyer', 'status', 'created_at', 'updated_at']


