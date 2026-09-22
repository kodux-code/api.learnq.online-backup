from rest_framework import serializers
from django.db.models import Sum
from .models import (
    Bundle, Coupon,
    SubscriptionPlan, Subscription, SubscriptionInvoice,
    Refund, WebhookEvent, PaymentGateway
)
from client.serializers import PublicProfileSerializer
from course.serializers import CourseListSerializer

# Use unified transaction model for order serialization
from transaction.serializers import TransactionSerializer as UnifiedTransactionSerializer
from transaction.serializers import TransactionListSerializer as UnifiedTransactionListSerializer


class BundleSerializer(serializers.ModelSerializer):
    courses = CourseListSerializer(many=True, read_only=True)
    course_count = serializers.IntegerField(read_only=True)
    discount_percentage = serializers.IntegerField(read_only=True)

    class Meta:
        model = Bundle
        fields = [
            'id', 'title', 'slug', 'description', 'thumbnail',
            'courses', 'course_count', 'original_price', 'sale_price',
            'discount_percentage', 'is_active', 'is_featured',
            'valid_from', 'valid_until', 'max_uses', 'used_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'used_count', 'created_at', 'updated_at']


class BundleCreateSerializer(serializers.ModelSerializer):
    course_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True)

    class Meta:
        model = Bundle
        fields = [
            'title', 'slug', 'description', 'thumbnail',
            'course_ids', 'original_price', 'sale_price',
            'is_active', 'is_featured', 'valid_from', 'valid_until', 'max_uses'
        ]

    def create(self, validated_data):
        course_ids = validated_data.pop('course_ids', [])
        bundle = Bundle.objects.create(**validated_data)
        bundle.courses.set(course_ids)
        return bundle

    def update(self, instance, validated_data):
        course_ids = validated_data.pop('course_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if course_ids is not None:
            instance.courses.set(course_ids)
        return instance


class CouponSerializer(serializers.ModelSerializer):
    applicable_courses = CourseListSerializer(many=True, read_only=True)
    is_valid_now = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'name', 'description',
            'discount_type', 'discount_value', 'max_discount_amount',
            'scope', 'applicable_courses', 'applicable_categories', 'applicable_bundles',
            'usage_limit', 'usage_limit_per_user', 'used_count',
            'valid_from', 'valid_until', 'is_active', 'is_auto_apply',
            'minimum_order_amount', 'new_users_only',
            'is_valid_now', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'used_count', 'created_at', 'updated_at']


class CouponCreateSerializer(serializers.ModelSerializer):
    course_ids = serializers.ListField(child=serializers.UUIDField(), required=False, write_only=True)
    category_ids = serializers.ListField(child=serializers.UUIDField(), required=False, write_only=True)
    bundle_ids = serializers.ListField(child=serializers.UUIDField(), required=False, write_only=True)

    class Meta:
        model = Coupon
        fields = [
            'code', 'name', 'description',
            'discount_type', 'discount_value', 'max_discount_amount',
            'scope', 'course_ids', 'category_ids', 'bundle_ids',
            'usage_limit', 'usage_limit_per_user',
            'valid_from', 'valid_until', 'is_active', 'is_auto_apply',
            'minimum_order_amount', 'new_users_only'
        ]

    def validate(self, attrs):
        if attrs['valid_from'] >= attrs['valid_until']:
            raise serializers.ValidationError("valid_from must be before valid_until.")
        return attrs

    def create(self, validated_data):
        course_ids = validated_data.pop('course_ids', [])
        category_ids = validated_data.pop('category_ids', [])
        bundle_ids = validated_data.pop('bundle_ids', [])

        validated_data['created_by'] = self.context['request'].user
        coupon = Coupon.objects.create(**validated_data)

        if course_ids:
            coupon.applicable_courses.set(course_ids)
        if category_ids:
            coupon.applicable_categories.set(category_ids)
        if bundle_ids:
            coupon.applicable_bundles.set(bundle_ids)

        return coupon

    def update(self, instance, validated_data):
        course_ids = validated_data.pop('course_ids', None)
        category_ids = validated_data.pop('category_ids', None)
        bundle_ids = validated_data.pop('bundle_ids', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if course_ids is not None:
            instance.applicable_courses.set(course_ids)
        if category_ids is not None:
            instance.applicable_categories.set(category_ids)
        if bundle_ids is not None:
            instance.applicable_bundles.set(bundle_ids)

        return instance


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField()
    order_amount = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    items = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class CouponValidateResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    message = serializers.CharField()
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'slug', 'description',
            'price', 'currency', 'interval', 'interval_count',
            'trial_days', 'setup_fee', 'features',
            'max_courses', 'includes_bundles',
            'is_active', 'is_featured', 'sort_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'stripe_price_id', 'stripe_product_id', 'created_at', 'updated_at']


class SubscriptionPlanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'name', 'slug', 'description',
            'price', 'currency', 'interval', 'interval_count',
            'trial_days', 'setup_fee', 'features',
            'max_courses', 'includes_bundles',
            'is_active', 'is_featured', 'sort_order'
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    user = PublicProfileSerializer(read_only=True)
    is_active_subscription = serializers.BooleanField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'user', 'plan', 'status',
            'price', 'currency', 'interval',
            'current_period_start', 'current_period_end',
            'trial_end', 'cancel_at_period_end',
            'cancellation_reason', 'cancelled_at', 'ended_at',
            'is_active_subscription', 'days_remaining',
            'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'plan', 'status', 'price', 'currency',
            'interval', 'current_period_start', 'current_period_end',
            'trial_end', 'cancelled_at', 'ended_at', 'created_at', 'updated_at'
        ]


class SubscriptionCreateSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    payment_method_id = serializers.CharField(required=False, allow_blank=True)
    trial_days = serializers.IntegerField(required=False, default=0)


class SubscriptionInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionInvoice
        fields = [
            'id', 'subscription', 'transaction', 'stripe_invoice_id',
            'amount', 'currency', 'status',
            'period_start', 'period_end', 'paid_at', 'created_at'
        ]
        read_only_fields = fields


class RefundSerializer(serializers.ModelSerializer):
    transaction = serializers.SerializerMethodField()
    requested_by = PublicProfileSerializer(read_only=True)
    approved_by = PublicProfileSerializer(read_only=True)

    class Meta:
        model = Refund
        fields = [
            'id', 'transaction', 'user', 'amount', 'reason', 'reason_details',
            'status', 'gateway_refund_id',
            'requested_by', 'approved_by', 'approved_at',
            'processed_at', 'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'transaction', 'user', 'amount', 'reason', 'reason_details',
            'status', 'gateway_refund_id', 'gateway_response',
            'requested_by', 'approved_by', 'approved_at',
            'processed_at', 'completed_at', 'created_at', 'updated_at'
        ]

    def get_transaction(self, obj):
        from transaction.serializers import TransactionSerializer as UnifiedTransactionSerializer
        if obj.transaction:
            return UnifiedTransactionSerializer(obj.transaction).data
        return None


class RefundRequestSerializer(serializers.Serializer):
    transaction_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    reason = serializers.ChoiceField(choices=Refund.Reason.choices)
    reason_details = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Refund amount must be positive.")
        return value


class RefundActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject', 'process'])
    reason = serializers.CharField(required=False, allow_blank=True)


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = [
            'id', 'gateway', 'event_type', 'event_id',
            'payload', 'processed', 'processing_error',
            'received_at', 'processed_at'
        ]
        read_only_fields = fields

class WalletTopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    gateway = serializers.ChoiceField(choices=PaymentGateway.choices)
    payment_method_id = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        if value > 10000:
            raise serializers.ValidationError("Maximum top-up amount is 10,000.")
        return value