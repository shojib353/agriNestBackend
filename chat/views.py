from rest_framework import viewsets, permissions, status,serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import ChatConnection, Message
from .serializers import ChatConnectionSerializer, MessageSerializer,ShowAllUserSerializer
from django.contrib.auth import get_user_model

User=get_user_model()



class ChatConnectionViewSet(viewsets.ModelViewSet):
    serializer_class = ChatConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Users can only see connections where they are the sender OR receiver
        return ChatConnection.objects.filter(Q(sender=user) | Q(receiver=user))
    
    # --- OVERRIDE CREATE TO HANDLE "GET OR CREATE" LOGIC ---
    def create(self, request, *args, **kwargs):
        user = request.user
        # Get receiver_id from the incoming request (could be 'receiver' or 'receiver_id' depending on your serializer)
        receiver_id = request.data.get('receiver_id') or request.data.get('receiver')

        if receiver_id:
            # Check if a chat connection already exists between these two users in ANY direction
            existing_connection = ChatConnection.objects.filter(
                (Q(sender=user) & Q(receiver_id=receiver_id)) |
                (Q(sender_id=receiver_id) & Q(receiver=user))
            ).first()

            if existing_connection:
                # Chat already exists! Return it with a 200 OK status
                serializer = self.get_serializer(existing_connection)
                return Response(serializer.data, status=status.HTTP_200_OK)

        # If it doesn't exist, proceed with the standard creation (which calls perform_create)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # The logged-in user is strictly the sender
        serializer.save(sender=self.request.user)

    # --- CUSTOM ACTIONS FOR MUTUAL APPROVAL ---

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        connection = self.get_object()
        
        # Only the receiver can accept the request
        if connection.receiver != request.user:
            return Response({"detail": "You cannot accept a request you didn't receive."}, status=status.HTTP_403_FORBIDDEN)
            
        connection.status = ChatConnection.ConnectionStatus.ACCEPTED
        connection.save()
        return Response({"status": "Chat request accepted!"})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        connection = self.get_object()
        
        if connection.receiver != request.user:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
        connection.status = ChatConnection.ConnectionStatus.REJECTED
        connection.save()
        return Response({"status": "Chat request rejected."})

    @action(detail=True, methods=['post'])
    def block(self, request, pk=None):
        connection = self.get_object()
        
        # Either the sender or receiver can block at any time
        if request.user not in [connection.sender, connection.receiver]:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
        connection.status = ChatConnection.ConnectionStatus.BLOCKED
        connection.save()
        return Response({"status": "User blocked."})


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        connection_id = self.request.query_params.get('connection_id')

        # Base query: Only show messages from connections the user is a part of
        queryset = Message.objects.filter(
            Q(connection__sender=user) | Q(connection__receiver=user)
        )

        # Filter by a specific chat room if requested (e.g. /messages/?connection_id=1)
        if connection_id:
            queryset = queryset.filter(connection_id=connection_id)
            
        return queryset.order_by('-timestamp')

    def perform_create(self, serializer):
        connection = serializer.validated_data['connection']
        user = self.request.user

        # SECURITY: Ensure the user is actually part of this connection
        if user not in [connection.sender, connection.receiver]:
            raise serializers.ValidationError("You are not part of this chat.")
            
        # SECURITY: Ensure the connection is actually ACCEPTED before allowing messages
        if connection.status != ChatConnection.ConnectionStatus.ACCEPTED:
            raise serializers.ValidationError("Chat request must be accepted before sending messages.")

        serializer.save(sender=user)

class ShowAllUserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = ShowAllUserSerializer
    permission_classes = [permissions.IsAuthenticated]
