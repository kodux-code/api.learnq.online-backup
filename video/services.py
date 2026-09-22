import logging
from datetime import timedelta
from django.conf import settings
from livekit import api

logger = logging.getLogger(__name__)

def generate_livekit_token(user, room_name: str, is_publisher: bool) -> str:
    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(str(user.id))
        .with_name(user.display_name or user.first_name)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=is_publisher,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(timedelta(hours=2))
    )
    return token.to_jwt()

async def create_restricted_room(room_name: str, max_participants: int):
    lkapi = api.LiveKitAPI(
        settings.LIVEKIT_WS_URL.replace("wss://", "https://"),
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET
    )
    try:
        await lkapi.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                empty_timeout=5 * 60, 
                max_participants=max_participants, 
            )
        )
    except Exception as e:
        logger.error("Failed to provision LiveKit room: %s", e)
    finally:
        await lkapi.aclose()

async def get_active_participant_count(room_name: str) -> int:
    lkapi = api.LiveKitAPI(
        settings.LIVEKIT_WS_URL.replace("wss://", "https://"),
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET
    )
    try:
        res = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        count = len(res.participants)
    except Exception:
        count = 0
    finally:
        await lkapi.aclose()
    return count