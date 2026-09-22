import json
import time
import uuid

from django.core.cache import cache
from django.db import transaction

from message.models import Thread


CALL_TTL_SECONDS = 60
ACTIVE_CALL_TTL_SECONDS = 4 * 60 * 60
LIVE_STATUSES = {"ringing", "active"}


def _key(thread_id):
    return f"call:thread:{thread_id}"


class CallState:
    @staticmethod
    def _get_unlocked(thread_id):
        raw = cache.get(_key(thread_id))
        return json.loads(raw) if raw else None

    @staticmethod
    def _lock_thread(thread_id):
        # Locking the parent thread gives cache mutations a transactional mutex.
        # All call-state mutations must go through this class.
        Thread.objects.select_for_update().get(pk=thread_id)

    @staticmethod
    def get(thread_id):
        return CallState._get_unlocked(thread_id)

    @staticmethod
    def start(thread_id, caller_id, invited_user_ids):
        with transaction.atomic():
            CallState._lock_thread(thread_id)
            existing = CallState._get_unlocked(thread_id)
            if existing and existing.get("status") in LIVE_STATUSES:
                return None

            state = {
                "call_id": str(uuid.uuid4()),
                "status": "ringing",
                "caller_id": str(caller_id),
                "invited_user_ids": [str(user_id) for user_id in invited_user_ids],
                "joined_user_ids": [],
                "declined_user_ids": [],
                "created_at": time.time(),
            }
            cache.set(_key(thread_id), json.dumps(state), timeout=CALL_TTL_SECONDS)
            return state

    @staticmethod
    def authorize_join(thread_id, user_id, call_id):
        """Validate a join without recording a media presence yet."""
        state = CallState._get_unlocked(thread_id)
        if not state or state.get("call_id") != str(call_id):
            return None
        if state.get("status") not in LIVE_STATUSES:
            return None

        user_id = str(user_id)
        eligible = user_id == state.get("caller_id") or user_id in state.get("invited_user_ids", [])
        if not eligible or user_id in state.get("declined_user_ids", []):
            return None
        return state

    @staticmethod
    def activate_for_join(thread_id, user_id, call_id):
        """Record an accepted join after LiveKit room preparation succeeds."""
        with transaction.atomic():
            CallState._lock_thread(thread_id)
            state = CallState.authorize_join(thread_id, user_id, call_id)
            if not state:
                return None

            state["status"] = "active"
            user_id = str(user_id)
            if user_id not in state["joined_user_ids"]:
                state["joined_user_ids"].append(user_id)
            cache.set(_key(thread_id), json.dumps(state), timeout=ACTIVE_CALL_TTL_SECONDS)
            return state

    @staticmethod
    def decline(thread_id, user_id, call_id):
        with transaction.atomic():
            CallState._lock_thread(thread_id)
            state = CallState._get_unlocked(thread_id)
            user_id = str(user_id)
            if (
                not state
                or state.get("call_id") != str(call_id)
                or state.get("status") not in LIVE_STATUSES 
                or user_id not in state.get("invited_user_ids", [])
            ):
                return None

            if user_id not in state["declined_user_ids"]:
                state["declined_user_ids"].append(user_id)

            if set(state["declined_user_ids"]) >= set(state["invited_user_ids"]):
                state["status"] = "ended"
                cache.delete(_key(thread_id))
            else:
                cache.set(_key(thread_id), json.dumps(state), timeout=CALL_TTL_SECONDS)
            return state

    @staticmethod
    def end(thread_id, actor_id, call_id, *, allowed_statuses):
        with transaction.atomic():
            CallState._lock_thread(thread_id)
            state = CallState._get_unlocked(thread_id)
            if (
                not state
                or state.get("call_id") != str(call_id)
                or state.get("status") not in allowed_statuses
                or state.get("caller_id") != str(actor_id)
            ):
                return None

            state["status"] = "ended"
            cache.delete(_key(thread_id))
            return state
