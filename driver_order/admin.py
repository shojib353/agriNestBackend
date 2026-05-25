from django.contrib import admin
from .models import DriverProfile, DriverOrder



@admin.register(DriverOrder)
class DriverOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'buyer', 'driver', 'job_date', 'agreed_price', 'status', 'created_at')
    list_filter = ('status', 'job_date')
    search_fields = ('buyer__username', 'driver__user__username', 'pickup_location')
    
    # Super handy: Update a job's status instantly from the list view
    list_editable = ('status',)
    
    # Organize the detail view into logical sections for a cleaner look
    fieldsets = (
        ('People Involved', {
            'fields': ('buyer', 'driver')
        }),
        ('Job Details', {
            'fields': ('pickup_location', 'dropoff_location', 'job_description', 'job_date')
        }),
        ('Pricing & Status', {
            'fields': ('agreed_price', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',) # Hides the timestamps by default to save screen space
        }),
    )
    
    # These fields are auto-generated, so we make them read-only in the admin panel
    readonly_fields = ('created_at', 'updated_at')