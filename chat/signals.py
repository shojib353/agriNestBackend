from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Import your models and serializer
from .models import Message 
from .serializers import ChatConnectionSerializer

@receiver(post_save, sender=Message)
def broadcast_connection_update(sender, instance, created, **kwargs):
    if created:
        # Assuming your Message model has a ForeignKey to ChatConnection named 'connection'
        connection = instance.connection 
        channel_layer = get_channel_layer()

        # The users we need to notify
        users_to_notify = [connection.sender, connection.receiver]

        for user in users_to_notify:
            # NOTE: Because your serializer has `is_sender_me`, which usually relies on 
            # `request.user`, we fake a context object here so the serializer doesn't crash.
            class MockRequest:
                def __init__(self, user):
                    self.user = user

            serializer = ChatConnectionSerializer(
                connection, 
                context={'request': MockRequest(user)}
            )
            
            # Send to this specific user's WebSocket group
            group_name = f"user_connections_{user.id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "connection_update",  # Matches the consumer method name
                    "data": serializer.data
                }
            )