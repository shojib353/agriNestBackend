import json
import base64
from django.core.files.base import ContentFile
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder

from agriAuthentication.models import FCMToken
from firebase_admin import messaging

from .models import ChatConnection, Message
from .serializers import MessageSerializer


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.connection_id = self.scope['url_route']['kwargs']['connection_id']
        self.room_group_name = f'chat_{self.connection_id}'

        if isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        is_authorized = await self.check_chat_access(self.user.id, self.connection_id)
        print(f"User {self.user.id} authorization for connection {self.connection_id}: {is_authorized}")
        
        if not is_authorized:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Routes incoming WebSocket JSON to the correct handler based on 'type'
        """
        text_data_json = json.loads(text_data)
        event_type = text_data_json.get('type')

        # Dispatch dictionary
        handlers = {
            # Standard Chat Features
            'chat_message': self.handle_chat_message,
            'media_message': self.handle_media_message,
            'typing': self.handle_typing,
            'mark_read': self.handle_mark_read,
            
            # Call & WebRTC Signaling
            'call_initiate': self.handle_call_initiate,
            'call_accept': self.handle_call_accept,
            'call_reject': self.handle_call_reject,
            'call_end': self.handle_call_end,
            'offer': self.handle_offer,
            'answer': self.handle_answer,
            'ice_candidate': self.handle_ice_candidate,
            'ping': self.handle_ping,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(text_data_json)
        else:
            print(f"Unknown or missing event type: {event_type}")

    # --- STANDARD CHAT HANDLERS (Fixing the missing methods) ---

    async def handle_chat_message(self, data):
        message_content = data.get('message')
        if not message_content:
            return

        message_data = await self.save_text_message(self.user.id, self.connection_id, message_content)
        await self.send_push_notification(self.connection_id, self.user.id, message_content, msg_type="chat_message")
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message': message_data
            }
        )
        await self.notify_conversation_list_update(self.connection_id)

    async def handle_media_message(self, data):
        message_type = data.get('message_type') 
        file_name = data.get('file_name')
        file_data = data.get('file_data')       
        content = data.get('message', '')       

        if not all([message_type, file_name, file_data]):
            return

        # Extract the raw base64 string
        if ';base64,' in file_data:
            format_str, base64_str = file_data.split(';base64,')
        else:
            base64_str = file_data

        # Base64 strings must be a multiple of 4 in length.
        padding_needed = len(base64_str) % 4
        if padding_needed > 0:
            base64_str += '=' * (4 - padding_needed)

        try:
            decoded_file = base64.b64decode(base64_str, validate=True)
            file_obj = ContentFile(decoded_file, name=file_name)
            
            message_data = await self.save_media_message(
                self.user.id, 
                self.connection_id, 
                message_type, 
                content, 
                file_obj
            )
            
            notification_text = content if content else f"Sent a {message_type.replace('_', ' ')}"
            await self.send_push_notification(self.connection_id, self.user.id, notification_text, msg_type=message_type)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_message',
                    'message': message_data
                }
            )
            await self.notify_conversation_list_update(self.connection_id)
        except Exception as e:
            print(f"Error decoding base64 or saving file ({type(e).__name__}): {e}")

    async def handle_typing(self, data):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_typing',
                'sender_id': self.user.id,
                'is_typing': data.get('is_typing', False)
            }
        )

    async def handle_mark_read(self, data):
        await self.mark_conversation_read(self.user.id, self.connection_id)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_read_receipt',
                'reader_id': self.user.id
            }
        )

    # --- CALL SIGNALING HANDLERS ---

    async def handle_call_initiate(self, data):
        """Step 1: Caller starts ringing the receiver."""
        is_video = data.get('data', {}).get('is_video', False)
        call_label = "Video" if is_video else "Audio"
        
        # Wake up the receiver with a push notification
        await self.send_push_notification(
            self.connection_id, 
            self.user.id, 
            f"📞 Incoming {call_label} Call", 
            msg_type="call_initiate"
        )
        
        # Broadcast to the room so the receiver's UI shows the incoming call screen
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'call_initiate',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )

    async def handle_call_accept(self, data):
        """Step 2: Receiver accepts. Tells caller to generate the WebRTC offer."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'call_accept',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )

    async def handle_call_reject(self, data):
        """Receiver declines the call."""
        call_type = data.get('call_type', Message.MessageType.AUDIO_CALL)
        
        # Save a missed/rejected call log (Duration 0)
        message_data = await self.save_call_log(self.user.id, self.connection_id, call_type, duration=0)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'call_reject',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )
        
        # Update chat list with the missed call message
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'broadcast_message', 'message': message_data}
        )
        await self.notify_conversation_list_update(self.connection_id)

    async def handle_call_end(self, data):
        """Either party hangs up an active call."""
        call_type = data.get('call_type', Message.MessageType.AUDIO_CALL)
        duration = data.get('duration', 0)
        
        # Save the finalized call log
        message_data = await self.save_call_log(self.user.id, self.connection_id, call_type, duration)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'call_end',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'broadcast_message', 'message': message_data}
        )
        await self.notify_conversation_list_update(self.connection_id)

    # --- WEBRTC NEGOTIATION HANDLERS ---

    async def handle_offer(self, data):
        """Step 3: Caller sends SDP Offer."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'offer',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )

    async def handle_answer(self, data):
        """Step 4: Receiver replies with SDP Answer."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'answer',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )

    async def handle_ice_candidate(self, data):
        """Step 5: Peers exchange ICE candidates to establish P2P connection."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_webrtc_signal',
                'signal_type': 'ice_candidate',
                'data': data.get('data', {}),
                'sender_id': self.user.id
            }
        )

    # --- UTILITY HANDLERS ---

    async def handle_ping(self, data):
        """Keep-alive connection to prevent WebSocket timeout."""
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'status': 'ok'
        }))

    # --- BROADCAST HANDLERS ---

    async def broadcast_message(self, event):
        """Sends the final serialized payload to the WebSocket client."""
        await self.send(text_data=json.dumps({
            'type': 'chat_message', 
            'message': event['message']
        }))

    async def broadcast_typing(self, event):
        if self.user.id != event['sender_id']:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'sender_id': event['sender_id'],
                'is_typing': event['is_typing']
            }))

    async def broadcast_read_receipt(self, event):
        if self.user.id != event['reader_id']:
            await self.send(text_data=json.dumps({
                'type': 'read_receipt',
                'reader_id': event['reader_id']
            }))

    async def broadcast_webrtc_signal(self, event):
        if self.user.id != event['sender_id']:
            await self.send(text_data=json.dumps({
                'type': event['signal_type'],
                'data': event['data'],
                'sender_id': event['sender_id']
            }))

    # --- ASYNC DATABASE HELPERS ---

    @database_sync_to_async
    def send_push_notification(self, connection_id, sender_id, text_content, msg_type="chat_message"):
        try:
            connection = ChatConnection.objects.get(id=connection_id)
            receiver = connection.receiver if connection.sender.id == sender_id else connection.sender
            
            fcm_device = FCMToken.objects.filter(user=receiver).first()
            if not fcm_device:
                return 

            if msg_type == "webrtc_offer":
                message = messaging.Message(
                    data={
                        "connection_id": str(connection_id),
                        "type": msg_type,
                        "title": f"Incoming Call from {self.user.full_name}",
                        "body": text_content
                    },
                    token=fcm_device.token,
                )
            else:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=f"New message from {self.user.full_name}",
                        body=text_content[:50] + ("..." if len(text_content) > 50 else ""),
                    ),
                    data={
                        "connection_id": str(connection_id),
                        "type": msg_type
                    },
                    token=fcm_device.token,
                )
                
            messaging.send(message)
            
        except Exception as e:
            print(f"Error sending push notification: {e}")

    @database_sync_to_async
    def check_chat_access(self, user_id, connection_id):
        try:
            user_id_int = int(user_id) 
            connection = ChatConnection.objects.get(id=connection_id)
            if connection.status == ChatConnection.ConnectionStatus.ACCEPTED:
                if user_id_int in [connection.sender.id, connection.receiver.id]:
                    return True
            return False
        except ChatConnection.DoesNotExist:
            return False

    @database_sync_to_async
    def save_text_message(self, user_id, connection_id, content):
        msg = Message.objects.create(
            sender_id=user_id, 
            connection_id=connection_id, 
            message_type=Message.MessageType.TEXT,
            content=content
        )
        return MessageSerializer(msg).data

    @database_sync_to_async
    def save_media_message(self, user_id, connection_id, message_type, content, file_obj):
        msg = Message.objects.create(
            sender_id=user_id,
            connection_id=connection_id,
            message_type=message_type,
            content=content,
            attachment=file_obj
        )
        return MessageSerializer(msg).data

    @database_sync_to_async
    def save_call_log(self, user_id, connection_id, call_type, duration):
        content = "📞 Audio Call Ended" if call_type == Message.MessageType.AUDIO_CALL else "📹 Video Call Ended"
        msg = Message.objects.create(
            sender_id=user_id,
            connection_id=connection_id,
            message_type=call_type,
            content=content,
            call_duration=duration
        )
        return MessageSerializer(msg).data

    @database_sync_to_async
    def mark_conversation_read(self, user_id, connection_id):
        Message.objects.filter(
            connection_id=connection_id,
            is_read=False
        ).exclude(
            sender_id=user_id
        ).update(is_read=True)

    @database_sync_to_async
    def get_connection_updates(self, connection_id):
        from .serializers import ChatConnectionSerializer 
        from .models import ChatConnection

        connection = ChatConnection.objects.get(id=connection_id)
        updates = []
        
        for user_instance in [connection.sender, connection.receiver]:
            class MockRequest:
                def __init__(self, u):
                    self.user = u
                
                def build_absolute_uri(self, url):
                    return url 
                    
            try:
                serializer = ChatConnectionSerializer(
                    connection, 
                    context={'request': MockRequest(user_instance)}
                )
                
                safe_data = json.loads(json.dumps(serializer.data, cls=DjangoJSONEncoder))
                
                updates.append({
                    'user_id': user_instance.id,
                    'data': safe_data
                })
            except Exception as e:
                print(f"❌ SERIALIZER CRASH for user {user_instance.id}: {e}")
                
        return updates

    async def notify_conversation_list_update(self, connection_id):
        try:
            updates = await self.get_connection_updates(connection_id)
            for update in updates:
                group_name = f"user_connections_{update['user_id']}"
                
                await self.channel_layer.group_send(
                    group_name,
                    {
                        'type': 'connection_update', 
                        'data': update['data']
                    }
                )
        except Exception as e:
            print(f"❌ Error in notify_conversation_list_update: {e}")


# ========================================================================= #
# Chat Connection Consumer
# ========================================================================= #

class ChatConnectionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_anonymous:
            await self.close()
        else:
            self.group_name = f"user_connections_{self.user.id}"
            
            await self.channel_layer.group_add(
                self.group_name, 
                self.channel_name
            )
            await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name, 
                self.channel_name
            )

    async def connection_update(self, event):
        connection_data = event['data']
        
        await self.send(text_data=json.dumps({
            'type': 'connection_update',
            'connection': connection_data
        }, cls=DjangoJSONEncoder))





























# import json
# import base64
# from django.core.files.base import ContentFile
# from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.db import database_sync_to_async
# from django.contrib.auth.models import AnonymousUser
# from django.utils import timezone
# from django.db.models import Q

# from agriAuthentication.models import FCMToken
# from firebase_admin import messaging

# from .models import ChatConnection, Message
# from .serializers import MessageSerializer  # <-- Ensure this is imported correctly
# from django.core.serializers.json import DjangoJSONEncoder

# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.user = self.scope["user"]
#         self.connection_id = self.scope['url_route']['kwargs']['connection_id']
#         self.room_group_name = f'chat_{self.connection_id}'

#         if isinstance(self.user, AnonymousUser):
#             await self.close(code=4001)
#             return

#         is_authorized = await self.check_chat_access(self.user.id, self.connection_id)
#         print(f"User {self.user.id} authorization for connection {self.connection_id}: {is_authorized}")
#         if not is_authorized:
#             await self.close(code=4003)
#             return

#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()

#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

#     async def receive(self, text_data):
#         """
#         Routes incoming WebSocket JSON to the correct handler based on 'type'
#         """
#         text_data_json = json.loads(text_data)
#         event_type = text_data_json.get('type')

#         # 1. HANDLE STANDARD TEXT MESSAGES
#         if event_type == 'chat_message':
#             message_content = text_data_json.get('message')
#             if not message_content:
#                 return

#             # Now returns fully serialized data dictionary
#             message_data = await self.save_text_message(self.user.id, self.connection_id, message_content)
#             await self.send_push_notification(self.connection_id, self.user.id, message_content,msg_type="chat_message")
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'broadcast_message',
#                     'message': message_data
#                 }
#             )
#             await self.notify_conversation_list_update(self.connection_id)
            

#         # 2. HANDLE MEDIA UPLOADS (PHOTO, FILE, AUDIO, VIDEO) VIA BASE64
#         elif event_type == 'media_message':
#             message_type = text_data_json.get('message_type') 
#             file_name = text_data_json.get('file_name')
#             file_data = text_data_json.get('file_data')       
#             content = text_data_json.get('message', '')       

#             if not all([message_type, file_name, file_data]):
#                 return

#             # Extract the raw base64 string
#             if ';base64,' in file_data:
#                 format_str, base64_str = file_data.split(';base64,')
#             else:
#                 base64_str = file_data

#             # Base64 strings must be a multiple of 4 in length.
#             padding_needed = len(base64_str) % 4
#             if padding_needed > 0:
#                 base64_str += '=' * (4 - padding_needed)

#             try:
#                 decoded_file = base64.b64decode(base64_str, validate=True)
#                 file_obj = ContentFile(decoded_file, name=file_name)
                
#                 # Now returns fully serialized data dictionary
#                 message_data = await self.save_media_message(
#                     self.user.id, 
#                     self.connection_id, 
#                     message_type, 
#                     content, 
#                     file_obj
#                 )
#                 notification_text = content if content else f"Sent a {message_type.replace('_', ' ')}"
#                 await self.send_push_notification(self.connection_id, self.user.id, notification_text, msg_type=message_type)

#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         'type': 'broadcast_message',
#                         'message': message_data
#                     }
#                 )
#                 await self.notify_conversation_list_update(self.connection_id)
#             except Exception as e:
#                 print(f"Error decoding base64 or saving file ({type(e).__name__}): {e}")

#         # 3. HANDLE TYPING INDICATORS
#         elif event_type == 'typing':
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'broadcast_typing',
#                     'sender_id': self.user.id,
#                     'is_typing': text_data_json.get('is_typing', False)
#                 }
#             )

#         # 4. HANDLE READ RECEIPTS
#         elif event_type == 'mark_read':
#             await self.mark_conversation_read(self.user.id, self.connection_id)
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'broadcast_read_receipt',
#                     'reader_id': self.user.id
#                 }
#             )

#         # 5. HANDLE WEBRTC SIGNALING
#         elif event_type in ['webrtc_offer', 'webrtc_answer', 'webrtc_ice_candidate', 'webrtc_end']:
            
#             if event_type == 'webrtc_offer':
#                 is_video = text_data_json.get('data', {}).get('is_video', False)
#                 call_label = "Video" if is_video else "Audio"
#                 await self.send_push_notification(self.connection_id, self.user.id, f"📞 Incoming {call_label} Call", "webrtc_offer")
            
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'broadcast_webrtc_signal',
#                     'signal_type': event_type,
#                     'data': text_data_json.get('data', {}),
#                     'sender_id': self.user.id
#                 }
#             )

#         # 6. HANDLE CALL END LOGS
#         elif event_type == 'call_ended':
#             call_type = text_data_json.get('call_type')
#             duration = text_data_json.get('duration', 0)
            
#             if call_type in [Message.MessageType.AUDIO_CALL, Message.MessageType.VIDEO_CALL]:
#                 # Now returns fully serialized data dictionary
#                 message_data = await self.save_call_log(self.user.id, self.connection_id, call_type, duration)
                
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         'type': 'broadcast_message',
#                         'message': message_data
#                     }
#                 )
#                 await self.notify_conversation_list_update(self.connection_id)

#     # --- BROADCAST HANDLERS ---

#     async def broadcast_message(self, event):
#         """
#         Sends the final serialized payload to the WebSocket client.
#         """
#         await self.send(text_data=json.dumps({
#             'type': 'chat_message', 
#             'message': event['message'] # Contains all fields from MessageSerializer
#         }))

#     async def broadcast_typing(self, event):
#         if self.user.id != event['sender_id']:
#             await self.send(text_data=json.dumps({
#                 'type': 'typing',
#                 'sender_id': event['sender_id'],
#                 'is_typing': event['is_typing']
#             }))

#     async def broadcast_read_receipt(self, event):
#         if self.user.id != event['reader_id']:
#             await self.send(text_data=json.dumps({
#                 'type': 'read_receipt',
#                 'reader_id': event['reader_id']
#             }))

#     async def broadcast_webrtc_signal(self, event):
#         if self.user.id != event['sender_id']:
#             await self.send(text_data=json.dumps({
#                 'type': event['signal_type'],
#                 'data': event['data'],
#                 'sender_id': event['sender_id']
#             }))

#     # --- ASYNC DATABASE HELPERS ---

#     @database_sync_to_async
#     def send_push_notification(self, connection_id, sender_id, text_content, msg_type="chat_message"):
#         try:
#             # 1. Identify the receiver
#             connection = ChatConnection.objects.get(id=connection_id)
#             receiver = connection.receiver if connection.sender.id == sender_id else connection.sender
            
#             # 2. Get the receiver's FCM token
#             fcm_device = FCMToken.objects.filter(user=receiver).first()
#             if not fcm_device:
#                 return 

#             # 3. Construct the message based on the type
#             if msg_type == "webrtc_offer":
#                 # 🔴 CALLS: Send DATA ONLY so Flutter can draw the Accept/Decline buttons
#                 message = messaging.Message(
#                     data={
#                         "connection_id": str(connection_id),
#                         "type": msg_type,
#                         "title": f"Incoming Call from {self.user.full_name}",
#                         "body": text_content
#                     },
#                     token=fcm_device.token,
                    
#                 )
#             else:
#                 # 🔵 CHAT MESSAGES: Standard notification handled by Android
#                 message = messaging.Message(
#                     notification=messaging.Notification(
#                         title=f"New message from {self.user.full_name}",
#                         body=text_content[:50] + ("..." if len(text_content) > 50 else ""),
#                     ),
#                     data={
#                         "connection_id": str(connection_id),
#                         "type": msg_type
#                     },
#                     token=fcm_device.token,
#                 )
                
#             messaging.send(message)
            
#         except Exception as e:
#             print(f"Error sending push notification: {e}")

#     # @database_sync_to_async
#     # def send_push_notification(self, connection_id, sender_id, text_content,msg_type="chat_message"):
#     #     try:
#     #         # 1. Identify the receiver
#     #         connection = ChatConnection.objects.get(id=connection_id)
#     #         receiver = connection.receiver if connection.sender.id == sender_id else connection.sender
            
#     #         # 2. Get the receiver's FCM token
#     #         fcm_device = FCMToken.objects.filter(user=receiver).first()
#     #         if not fcm_device:
#     #             return # Receiver hasn't registered a token

#     #         # 3. Construct and send the Firebase message
#     #         message = messaging.Message(
#     #             notification=messaging.Notification(
#     #                 title=f"New message from {self.user.full_name}",
#     #                 body=text_content[:50] + ("..." if len(text_content) > 50 else ""),
#     #             ),
#     #             data={
#     #                 "connection_id": str(connection_id),
#     #                 "type": msg_type
#     #             },
#     #             token=fcm_device.token,
#     #         )
#     #         messaging.send(message)
#     #         print(f"Push notification sent to {receiver.full_name} ({receiver.email}) with token {fcm_device.token}")
            
#     #     except Exception as e:
#     #         print(f"Error sending push notification: {e}")
    
#     @database_sync_to_async
#     def check_chat_access(self, user_id, connection_id):
#         try:
#             user_id_int = int(user_id) 
#             connection = ChatConnection.objects.get(id=connection_id)
#             if connection.status == ChatConnection.ConnectionStatus.ACCEPTED:
#                 if user_id_int in [connection.sender.id, connection.receiver.id]:
#                     return True
#             return False
#         except ChatConnection.DoesNotExist:
#             return False

#     @database_sync_to_async
#     def save_text_message(self, user_id, connection_id, content):
#         msg = Message.objects.create(
#             sender_id=user_id, 
#             connection_id=connection_id, 
#             message_type=Message.MessageType.TEXT,
#             content=content
#         )
#         # Evaluate .data inside the synchronous boundary
#         return MessageSerializer(msg).data

#     @database_sync_to_async
#     def save_media_message(self, user_id, connection_id, message_type, content, file_obj):
#         msg = Message.objects.create(
#             sender_id=user_id,
#             connection_id=connection_id,
#             message_type=message_type,
#             content=content,
#             attachment=file_obj
#         )
#         return MessageSerializer(msg).data

#     @database_sync_to_async
#     def save_call_log(self, user_id, connection_id, call_type, duration):
#         content = "📞 Audio Call Ended" if call_type == Message.MessageType.AUDIO_CALL else "📹 Video Call Ended"
#         msg = Message.objects.create(
#             sender_id=user_id,
#             connection_id=connection_id,
#             message_type=call_type,
#             content=content,
#             call_duration=duration
#         )
#         return MessageSerializer(msg).data

#     @database_sync_to_async
#     def mark_conversation_read(self, user_id, connection_id):
#         Message.objects.filter(
#             connection_id=connection_id,
#             is_read=False
#         ).exclude(
#             sender_id=user_id
#         ).update(is_read=True)

#     @database_sync_to_async
#     def get_connection_updates(self, connection_id):
#         from .serializers import ChatConnectionSerializer 
#         from .models import ChatConnection

#         connection = ChatConnection.objects.get(id=connection_id)
#         updates = []
        
#         for user_instance in [connection.sender, connection.receiver]:
#             class MockRequest:
#                 def __init__(self, u):
#                     self.user = u
                
#                 def build_absolute_uri(self, url):
#                     return url 
                    
#             try:
#                 serializer = ChatConnectionSerializer(
#                     connection, 
#                     context={'request': MockRequest(user_instance)}
#                 )
                
#                 # ✅ THE FIX: Force evaluation of all nested objects (like datetimes) 
#                 # into purely JSON-safe strings before handing it to Channels/Redis.
#                 safe_data = json.loads(json.dumps(serializer.data, cls=DjangoJSONEncoder))
                
#                 updates.append({
#                     'user_id': user_instance.id,
#                     'data': safe_data
#                 })
#             except Exception as e:
#                 print(f"❌ SERIALIZER CRASH for user {user_instance.id}: {e}")
                
#         return updates

#     # @database_sync_to_async
#     # def get_connection_updates(self, connection_id):
#     #     from .serializers import ChatConnectionSerializer 
#     #     from .models import ChatConnection

#     #     connection = ChatConnection.objects.get(id=connection_id)
#     #     updates = []
        
#     #     for user_instance in [connection.sender, connection.receiver]:
#     #         class MockRequest:
#     #             def __init__(self, u):
#     #                 self.user = u
                
#     #             def build_absolute_uri(self, url):
#     #                 return url 
                    
#     #         try:
#     #             serializer = ChatConnectionSerializer(
#     #                 connection, 
#     #                 context={'request': MockRequest(user_instance)}
#     #             )
#     #             updates.append({
#     #                 'user_id': user_instance.id,
#     #                 'data': serializer.data
#     #             })
#     #         except Exception as e:
#     #             print(f"❌ SERIALIZER CRASH for user {user_instance.id}: {e}")
                
#     #     return updates

#     async def notify_conversation_list_update(self, connection_id):
#         """
#         Fetches the latest connection state (last message, unread counts) 
#         and sends it to both the sender's and receiver's global connection groups.
#         """
#         try:
#             updates = await self.get_connection_updates(connection_id)
#             for update in updates:
#                 group_name = f"user_connections_{update['user_id']}"
                
#                 print(f"📡 Sending list update to group: {group_name}")
                
#                 await self.channel_layer.group_send(
#                     group_name,
#                     {
#                         'type': 'connection_update', 
#                         'data': update['data']
#                     }
#                 )
#         except Exception as e:
#             print(f"❌ Error in notify_conversation_list_update: {e}")







# # chat consumer/////////////////////////////////////////////////////////////////////////////////////////////////////


# import json
# from channels.generic.websocket import AsyncWebsocketConsumer

# class ChatConnectionConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.user = self.scope["user"]
        
#         # Reject unauthenticated users
#         if self.user.is_anonymous:
#             await self.close()
#         else:
#             # Create a unique group for this user's connections
#             self.group_name = f"user_connections_{self.user.id}"
            
#             await self.channel_layer.group_add(
#                 self.group_name, 
#                 self.channel_name
#             )
#             await self.accept()

#     async def disconnect(self, close_code):
#         if hasattr(self, 'group_name'):
#             await self.channel_layer.group_discard(
#                 self.group_name, 
#                 self.channel_name
#             )

#     # This method is triggered by the signal below
#     async def connection_update(self, event):
#         connection_data = event['data']
        
#         # Send the serialized data to the frontend
#         await self.send(text_data=json.dumps({
#             'type': 'connection_update',
#             'connection': connection_data
#         }, cls=DjangoJSONEncoder))

        
