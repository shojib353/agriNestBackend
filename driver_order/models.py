from django.db import models
from django.conf import settings

from agriAuthentication.models import DriverProfile

class DriverOrder(models.Model):
    class JobStatus(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'  # If driver declines the initial request
        COMPLETED = 'completed', 'Completed'
        CANCELLED_BY_BUYER = 'cancelled_by_buyer', 'Cancelled by Buyer'
        CANCELLED_BY_DRIVER = 'cancelled_by_driver', 'Cancelled by Driver'


    # Users involved
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='driver_orders'
    )
    driver = models.ForeignKey(
        DriverProfile, 
        on_delete=models.CASCADE, 
        related_name='job_orders'
    )

    # Job Details
    pickup_location = models.CharField(
        max_length=255, 
        help_text="Starting point or field location"
    )
    dropoff_location = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Destination (leave blank for stationary tractor work)"
    )
    job_date = models.DateTimeField(help_text="When is the service needed?")
    job_description = models.TextField(
        help_text="Details (e.g., 'Transport 50 sacks of rice' or 'Plow 2 acres of land')"
    )

    # Pricing & Status
    agreed_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Price agreed upon based on the driver's rate"
    )
    status = models.CharField(
        max_length=20, 
        choices=JobStatus.choices, 
        default=JobStatus.REQUESTED
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        # Fallback to username if full_name doesn't exist on your User model
        buyer_name = getattr(self.buyer, 'full_name', self.buyer.full_name) 
        return f"Job #{self.id} | {buyer_name} -> {self.driver.user.full_name} ({self.get_status_display()})"