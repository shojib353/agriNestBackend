from django.contrib import admin
from .models import ChatConnection, Message


@admin.register(ChatConnection)
class ChatConnectionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'sender',
        'receiver',
        'status',
        'created_at',
        'updated_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('sender__email', 'receiver__email')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'connection',
        'sender',
        'short_content',
        'is_read',
        'timestamp'
    )
    list_filter = ('is_read', 'timestamp')
    search_fields = ('sender__email', 'content')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

    def short_content(self, obj):
        return obj.content[:50]
    short_content.short_description = "Message"