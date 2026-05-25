from django.urls import re_path
from . import consumers

# This is the variable your asgi.py file is trying to import!
websocket_urlpatterns = [
    # The URL will look like: ws://127.0.0.1:8000/ws/chat/<connection_id>/
    re_path(r'ws/chat/(?P<connection_id>\w+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/connections/$', consumers.ChatConnectionConsumer.as_asgi()),
]

