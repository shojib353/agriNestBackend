
import os
from django.core.asgi import get_asgi_application
import django

# 1. Set the environment variable first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agriNest.settings')
django.setup()
# 2. Wake up Django and load the database models
django_asgi_app = get_asgi_application()

# 3. CRITICAL: Import your chat files DOWN HERE, *after* Django is awake
from channels.routing import ProtocolTypeRouter, URLRouter
from chat.routing import websocket_urlpatterns
from chat.middleware import JWTAuthMiddleware

# 4. Build the router
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(  # <-- Use the JWT middleware here
        URLRouter(
            websocket_urlpatterns
        )
    ),
})