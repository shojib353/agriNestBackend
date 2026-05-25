from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class ChatConnection(models.Model):
    class ConnectionStatus(models.TextChoices):
        PENDING = 'pending', 'Pending (Sent)'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        BLOCKED = 'blocked', 'Blocked'

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_chat_requests')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_chat_requests')
    status = models.CharField(max_length=20, choices=ConnectionStatus.choices, default=ConnectionStatus.PENDING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A user cannot send multiple requests to the same person
        unique_together = ('sender', 'receiver')

    def __str__(self):
        return f"{self.sender} -> {self.receiver} ({self.get_status_display()})"

    def clean(self):
        # Prevent a user from sending a request to themselves
        if self.sender == self.receiver:
            raise ValidationError("You cannot send a chat request to yourself.")


class Message(models.Model):
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        PHOTO = 'image', 'Image'
        FILE = 'file', 'File'
        AUDIO_NOTE = 'audio_note', 'Audio Note'
        AUDIO_CALL = 'audio_call', 'Audio Call Log'
        VIDEO_CALL = 'video_call', 'Video Call Log'

    connection = models.ForeignKey(ChatConnection, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages_sent')
    
    # 1. Distinguish what kind of message this is
    message_type = models.CharField(
        max_length=20, 
        choices=MessageType.choices, 
        default=MessageType.TEXT
    )
    
    # 2. Made blank=True because a photo/file might not have accompanying text
    content = models.TextField(blank=True, null=True, help_text="Text content or call status description (e.g., 'Missed Call')")
    
    # 3. Unified field for all media types (Photos, Files, Audio Notes)
    attachment = models.FileField(upload_to='chat_attachments/%Y/%m/', blank=True, null=True)
    
    # 4. Optional: To track how long an audio/video call lasted
    call_duration = models.PositiveIntegerField(blank=True, null=True, help_text="Duration in seconds")
    
    is_read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.get_message_type_display()}] From {self.sender} at {self.timestamp.strftime('%H:%M')}"
        
    def clean(self):
        # Validation: Ensure media messages have an attachment
        media_types = [self.MessageType.PHOTO, self.MessageType.FILE, self.MessageType.AUDIO_NOTE]
        if self.message_type in media_types and not self.attachment:
            raise ValidationError(f"An attachment is required for message type: {self.get_message_type_display()}")
            
        # Validation: Ensure text messages have content
        if self.message_type == self.MessageType.TEXT and not self.content:
            raise ValidationError("Text messages must contain content.")