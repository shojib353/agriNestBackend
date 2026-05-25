from django.contrib import admin
from .models import Post, PostImage, Like, Comment, Report


# -------------------------
# Inline for Post Images
# -------------------------
class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 1


# -------------------------
# Post Admin
# -------------------------
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'post_type', 'is_active', 'created_at')
    list_filter = ('post_type', 'is_active', 'created_at')
    search_fields = ('author__username', 'content')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PostImageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')


# -------------------------
# Like Admin
# -------------------------
@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'post__id')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'post')


# -------------------------
# Comment Admin
# -------------------------
@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'post', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('author__username', 'content')
    actions = ['approve_comments', 'hide_comments']

    def approve_comments(self, request, queryset):
        queryset.update(is_active=True)

    def hide_comments(self, request, queryset):
        queryset.update(is_active=False)

    approve_comments.short_description = "Approve selected comments"
    hide_comments.short_description = "Hide selected comments"


# -------------------------
# Report Admin
# -------------------------
@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reason', 'reporter__username')
    readonly_fields = ('created_at',)

    actions = ['mark_reviewed']

    def mark_reviewed(self, request, queryset):
        queryset.update(status=Report.ReportStatus.REVIEWED)

    mark_reviewed.short_description = "Mark selected reports as reviewed"