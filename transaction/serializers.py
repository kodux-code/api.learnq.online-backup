from rest_framework import serializers
from django.db.models import Sum, Count

from message.serializers import MinimalUserSerializer
from .models import Transaction, Wallet, WalletTransaction
from course.serializers import CourseListSerializer


class TransactionSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)
    counterparty = MinimalUserSerializer(read_only=True)
    teacher = MinimalUserSerializer(read_only=True)
    course = CourseListSerializer(read_only=True)
    payout = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'counterparty', 'teacher', 'course', 'enrollment', 'assessment',
            'order', 'subscription', 'bundle', 'payout',
            'direction', 'transaction_type', 'status',
            'amount', 'currency', 'net_amount', 'platform_fee',
            'gateway', 'gateway_transaction_id', 'gateway_transfer_id', 'gateway_payout_id',
            'gateway_response', 'revenue_share_percent', 'teacher_amount',
            'payout_method', 'description', 'metadata',
            'billing_email', 'billing_name', 'billing_address', 'billing_country',
            'ip_address', 'user_agent', 'coupon', 'coupon_code', 'discount_amount',
            'completed_at', 'failed_at', 'cancelled_at', 'expires_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'counterparty', 'teacher', 'course', 'enrollment', 'assessment',
            'order', 'subscription', 'bundle', 'payout',
            'direction', 'transaction_type', 'status',
            'amount', 'currency', 'net_amount', 'platform_fee',
            'gateway_transaction_id', 'gateway_transfer_id', 'gateway_payout_id',
            'gateway_response', 'revenue_share_percent', 'teacher_amount',
            'completed_at', 'failed_at', 'cancelled_at', 'expires_at',
            'created_at', 'updated_at'
        ]
    
    def get_payout(self, obj):
        if obj.payout:
            return {
                'id': str(obj.payout.id),
                'amount': str(obj.payout.amount),
                'status': obj.payout.status,
            }
        return None


class TransactionListSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)
    teacher = MinimalUserSerializer(read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    direction_display = serializers.CharField(source='get_direction_display', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'teacher', 'course', 'course_title',
            'direction', 'direction_display', 'transaction_type', 'type_display',
            'status', 'status_display',
            'amount', 'currency', 'net_amount', 'platform_fee', 'teacher_amount',
            'gateway', 'gateway_transaction_id',
            'completed_at', 'created_at'
        ]
        read_only_fields = fields


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'user', 'counterparty', 'teacher', 'course', 'enrollment', 'assessment',
            'order', 'subscription', 'bundle',
            'direction', 'transaction_type', 'status',
            'amount', 'currency', 'net_amount', 'platform_fee',
            'gateway', 'gateway_transaction_id', 'gateway_transfer_id', 'gateway_payout_id',
            'gateway_response', 'revenue_share_percent', 'teacher_amount',
            'payout_method', 'description', 'metadata',
            'billing_email', 'billing_name', 'billing_address', 'billing_country',
            'ip_address', 'user_agent', 'coupon', 'coupon_code', 'discount_amount',
            'expires_at'
        ]
    
    def validate(self, attrs):
        # Auto-set direction based on transaction_type if not provided
        direction = attrs.get('direction')
        transaction_type = attrs.get('transaction_type')
        
        if not direction and transaction_type:
            incoming_types = [
                'course_sale', 'subscription', 'bundle_sale',
                'upgrade', 'donation', 'refund_received'
            ]
            if transaction_type in incoming_types:
                attrs['direction'] = 'incoming'
            else:
                attrs['direction'] = 'outgoing'
        
        # Auto-set net_amount
        amount = attrs.get('amount', 0)
        platform_fee = attrs.get('platform_fee', 0)
        if 'net_amount' not in attrs:
            attrs['net_amount'] = amount - platform_fee
        
        return attrs


class TransactionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'status', 'gateway_response', 'description', 'metadata',
            'completed_at', 'failed_at', 'cancelled_at', 'expires_at',
            'gateway_transaction_id', 'gateway_transfer_id', 'gateway_payout_id',
            'payout', 'payout_method',
        ]


class WalletSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance', 'currency', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'balance', 'created_at', 'updated_at']


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'type', 'amount', 'balance_before', 'balance_after',
            'description', 'reference_id', 'reference_type',
            'metadata', 'created_at'
        ]
        read_only_fields = fields


class WalletTopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    gateway = serializers.ChoiceField(choices=[
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('razorpay', 'Razorpay'),
    ])
    payment_method_id = serializers.CharField(required=False, allow_blank=True)
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        if value > 10000:
            raise serializers.ValidationError("Maximum top-up amount is 10,000.")
        return value


class TransactionStatsSerializer(serializers.Serializer):
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payouts = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    transaction_count = serializers.IntegerField()
    by_type = serializers.DictField(child=serializers.DictField())
    by_status = serializers.DictField(child=serializers.IntegerField())
    by_month = serializers.ListField(child=serializers.DictField())