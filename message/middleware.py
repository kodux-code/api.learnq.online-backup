from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def get_user_from_access_token(raw_token: str):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        validated_token = AccessToken(raw_token)
        user_id = validated_token["user_id"]
        user = User.objects.select_related().get(pk=user_id, is_active=True)
        return user
    except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    """
    JWT Token authentication middleware for Django Channels.
    Expects token as query parameter: ?token=<access_token>
    """

    async def __call__(self, scope, receive, send):
        query_string = parse_qs(scope["query_string"].decode())
        token = query_string.get("token", [None])[0]

        scope["user"] = await get_user_from_access_token(token) if token else AnonymousUser()

        return await super().__call__(scope, receive, send)