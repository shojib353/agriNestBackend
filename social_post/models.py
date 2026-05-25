from django.db import models
from django.conf import settings
from products.models import Product  # Make sure this import matches your product app name

class Post(models.Model):
    class PostType(models.TextChoices):
        REGULAR = 'regular', 'Regular Post'
        PRODUCT = 'product', 'Product Linked Post'

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts')
    post_type = models.CharField(max_length=20, choices=PostType.choices, default=PostType.REGULAR)
    
    # Text content
    content = models.TextField(blank=True)
    
    # If it's a product post
    linked_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='social_posts')
    
    # If it's a shared post (repost)
    shared_post = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reposts')
    
    # Moderation
    is_active = models.BooleanField(default=True, help_text="Admins can set this to False to remove the post")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Post by {self.author} at {self.created_at.strftime('%Y-%m-%d')}"

class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='social_posts/')

class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post') # A user can only like a post once

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    is_active = models.BooleanField(default=True) # For moderation
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class Report(models.Model):
    class ReportStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        REVIEWED = 'reviewed', 'Reviewed & Resolved'

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)