from rest_framework import serializers
from django.db.models import Q

from agriAuthentication.models import User
from .models import ChatConnection, Message


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'role','location', 'photo','is_active',]

class ChatConnectionSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    receiver_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
        source='receiver'
    )
    last_message = serializers.SerializerMethodField(read_only=True)
    last_message_time = serializers.SerializerMethodField(read_only=True)
    last_message_type = serializers.SerializerMethodField(read_only=True)
    last_message_is_read = serializers.SerializerMethodField(read_only=True)
    last_sender = serializers.SerializerMethodField(read_only=True)
    is_sender_me=serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = ChatConnection
        fields = ['id', 'sender', 'receiver', 'receiver_id', 'last_message', 'last_message_time', 'last_message_type', 'last_message_is_read', 'last_sender', 'is_sender_me', 'status', 'created_at']
        # Status and sender are locked down for security
        read_only_fields = ['sender', 'status', 'created_at']

    def validate(self, attrs):
        request = self.context.get('request')
        receiver = attrs.get('receiver')

        # Check if a connection already exists in EITHER direction
        if ChatConnection.objects.filter(
            Q(sender=request.user, receiver=receiver) | 
            Q(sender=receiver, receiver=request.user)
        ).exists():
            raise serializers.ValidationError("A chat connection or request already exists between you two.")
            
        return attrs
    
    def get_last_message_obj(self, obj):
        return obj.messages.order_by('-timestamp').first()
    
    def get_last_message(self, obj):
        last_message = self.get_last_message_obj(obj)

        if not last_message:
            return None

        # If attachment message
        if last_message.message_type == Message.MessageType.PHOTO:
            return "📷 Photo"

        elif last_message.message_type == Message.MessageType.FILE:
            return "📁 File"

        elif last_message.message_type == Message.MessageType.AUDIO_NOTE:
            return "🎤 Audio Note"

        elif last_message.message_type == Message.MessageType.AUDIO_CALL:
            return "📞 Audio Call"

        elif last_message.message_type == Message.MessageType.VIDEO_CALL:
            return "📹 Video Call"

        # Text message
        return last_message.content
    
    
    def get_last_message_time(self, obj):
        last_message = self.get_last_message_obj(obj)
        return last_message.timestamp if last_message else None
    def get_last_message_type(self, obj):
        last_message = self.get_last_message_obj(obj)
        return last_message.message_type if last_message else None
    def get_last_message_is_read(self, obj):
        last_message = self.get_last_message_obj(obj)
        return last_message.is_read if last_message else None
    def get_last_sender(self, obj):
        last_message = self.get_last_message_obj(obj)
        return last_message.sender.id if last_message else None

    def get_is_sender_me(self, obj):
        last_message = self.get_last_message_obj(obj)
        return last_message.sender == self.context.get('request').user if last_message else None

class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.full_name', read_only=True)
    attachment = serializers.SerializerMethodField()


    class Meta:
        model = Message
        fields = ['id', 'connection', 'sender', 'sender_name', 'content', 'message_type','attachment','call_duration', 'is_read',  'timestamp']
        read_only_fields = ['sender', 'is_read', 'timestamp']   
    
    def get_attachment(self, obj):

        request = self.context.get('request')

        if obj.attachment:

            if request:
                return request.build_absolute_uri(
                    obj.attachment.url
                )

            return obj.attachment.url

        return None
    
class ShowAllUserSerializer(serializers.ModelSerializer):
    this_user_is_my_conversation_list = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField() # 🔥 Add the status field

    class Meta:
        model = User 
        fields = [
            'id', 'location', 'role', 'photo', 'full_name', 'phone', 'email', 
            'this_user_is_my_conversation_list', 
            'status' # 🔥 Ensure it is in the fields list
        ]
    
    # Keep your existing boolean logic if you still need it elsewhere
    def get_this_user_is_my_conversation_list(self, obj):
        request_user = self.context['request'].user
        return ChatConnection.objects.filter(
            Q(sender=request_user, receiver=obj) |
            Q(sender=obj, receiver=request_user)
        ).exists()

    # 🔥 Fetch the actual status string from the ChatConnection model
    def get_status(self, obj):
        request_user = self.context['request'].user
        
        # Use .first() to get the actual connection object instead of just a boolean
        connection = ChatConnection.objects.filter(
            Q(sender=request_user, receiver=obj) |
            Q(sender=obj, receiver=request_user)
        ).first()

        if connection:
            # Assuming your ChatConnection model has a field named 'status'
            # This will return 'pending', 'accepted', 'block', etc.
            return connection.status.lower() 
            
        # Return 'none' if no connection exists at all
        return 'none'