from rest_framework import serializers

from .models import PushSubscription


class CallSignalSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("ring", "decline", "cancel", "end"))
    call_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if attrs["action"] != "ring" and "call_id" not in attrs:
            raise serializers.ValidationError({"call_id": "This field is required for this action."})
        return attrs


class CallJoinSerializer(serializers.Serializer):
    call_id = serializers.UUIDField()


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ["endpoint", "p256dh", "auth"]
        extra_kwargs = {"endpoint": {"validators": []}}

    def create(self, validated_data):
        user = self.context["request"].user
        endpoint = validated_data["endpoint"]

        PushSubscription.objects.filter(endpoint=endpoint).exclude(user=user).delete()

        subscription, _ = PushSubscription.objects.update_or_create(
            user=user,
            endpoint=endpoint,
            defaults={
                "p256dh": validated_data["p256dh"],
                "auth": validated_data["auth"],
            },
        )
        return subscription
