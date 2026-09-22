import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.settings")
django_asgi_app = get_asgi_application()  # must init before importing consumers

from channels.routing import ProtocolTypeRouter, URLRouter
from message.middleware import TokenAuthMiddleware
from message.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})