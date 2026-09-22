from asgiref.sync import async_to_sync
from django.shortcuts import get_object_or_404
from channels.layers import get_channel_layer
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from message.models import Thread, ThreadParticipant
from message.permissions import IsThreadParticipant
from video.call_state import CallState
from video.tasks import send_call_push_notifications

from .serializers import CallJoinSerializer, CallSignalSerializer, PushSubscriptionSerializer
from .services import create_restricted_room, generate_livekit_token


import logging
from kombu.exceptions import OperationalError
logger = logging.getLogger(__name__)


class CallSignalThrottle(UserRateThrottle):
    scope = "call_signal"
    rate = "20/min"


def _room_limit(thread):
    return 2 if thread.thread_type == Thread.ThreadType.DIRECT else 50


def _broadcast(thread_id, action, extra_data):
    channel_layer = get_channel_layer()
    participants = ThreadParticipant.objects.filter(
        thread_id=thread_id, is_active=True
    ).select_related("user")
    for participant in participants:
        async_to_sync(channel_layer.group_send)(
            f"user_{participant.user_id}",
            {
                "type": "call_signal",
                "data": {"action": action, "thread_id": str(thread_id), **extra_data},
            },
        )
    return participants


class JoinThreadVideoView(APIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]
    throttle_classes = [CallSignalThrottle]

    def post(self, request, thread_id):
        serializer = CallJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        call_id = serializer.validated_data["call_id"]
        thread = get_object_or_404(Thread, id=thread_id)
        room_name = str(thread_id)
        state = CallState.authorize_join(thread_id, request.user.id, call_id)
        if not state:
            return Response({"detail": "This call is unavailable or you are not invited."}, status=409)
        try:
            async_to_sync(create_restricted_room)(room_name, _room_limit(thread))
        except Exception:
            return Response({"detail": "The video room is temporarily unavailable."}, status=503)
        state = CallState.activate_for_join(thread_id, request.user.id, call_id)
        if not state:
            return Response({"detail": "This call has ended."}, status=409)
        token = generate_livekit_token(request.user, room_name, is_publisher=True)
        _broadcast(thread_id, "joined", {
            "call_id": str(call_id),
            "user_id": str(request.user.id),
            "user_name": request.user.display_name,
        })
        return Response({"token": token, "room_id": room_name, "call_id": state["call_id"]})


class CallSignalView(APIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]
    throttle_classes = [CallSignalThrottle]

    def post(self, request, thread_id):
        serializer = CallSignalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        call_id = serializer.validated_data.get("call_id")
        thread = get_object_or_404(Thread, id=thread_id)

        others = list(
            ThreadParticipant.objects.filter(thread_id=thread_id, is_active=True)
            .exclude(user_id=request.user.id)
            .select_related("user")
        )

        if action == "ring":
            if not others:
                return Response({"detail": "No other active participants."}, status=404)
            state = CallState.start(thread_id, request.user.id, [participant.user_id for participant in others])
            if not state:
                existing_state = CallState.get(thread_id)
                existing_call_id = existing_state.get("call_id") if existing_state else None
                return Response({
                    "detail": "Call already in progress.",
                    "call_id": existing_call_id
                }, status=409)

            try:
                async_to_sync(create_restricted_room)(str(thread_id), _room_limit(thread))
            except Exception:
                CallState.end(thread_id, request.user.id, state["call_id"], allowed_statuses={"ringing"})
                return Response({"detail": "The video room is temporarily unavailable."}, status=503)

            _broadcast(thread_id, "ring", {
                "call_id": state["call_id"],
                "caller_id": str(request.user.id),
                "caller_name": request.user.display_name,
            })

            try:
                send_call_push_notifications.delay(
                    user_ids=[participant.user_id for participant in others],
                    caller_id=request.user.id,
                    caller_name=request.user.display_name,
                    thread_id=thread_id,
                )
            except OperationalError:
                logger.exception(
                    "Could not queue push notifications for video call in thread %s",
                    thread_id,
                )
            
            return Response({"call_id": state["call_id"], "notified": len(others)}, status=201)

        if action == "decline":
            state = CallState.decline(thread_id, request.user.id, call_id)
        elif action == "cancel":
            state = CallState.end(thread_id, request.user.id, call_id, allowed_statuses={"ringing"})
        else:  # action == "end"
            state = CallState.end(thread_id, request.user.id, call_id, allowed_statuses={"active"})

        if not state:
            return Response({"detail": "This call cannot be changed."}, status=409)

        _broadcast(thread_id, action, {
            "call_id": str(call_id),
            "user_id": str(request.user.id),
            "user_name": request.user.display_name,
        })
        return Response({"call_id": str(call_id), "notified": len(others)}, status=200)


class SavePushSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PushSubscriptionSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Subscription saved successfully."}, status=201)
