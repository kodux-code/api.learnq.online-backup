from rest_framework import serializers
from .models import TeacherEarning, Payout, PayoutSchedule, RevenueReport
from client.serializers import PublicProfileSerializer

# Use unified transaction model
from transaction.models import Transaction
from transaction.serializers import TransactionSerializer as UnifiedTransactionSerializer
from transaction.serializers import TransactionListSerializer as UnifiedTransactionListSerializer


class TeacherEarningSerializer(serializers.ModelSerializer):
    teacher = PublicProfileSerializer(read_only=True)
    pending_payout_display = serializers.DecimalField(max_digits=12, decimal_places=2, source='pending_payout', read_only=True)

    class Meta:
        model = TeacherEarning
        fields = [
            'id', 'teacher', 'total_earned', 'pending_payout', 'available_for_payout',
            'lifetime_payout', 'last_payout_at', 'last_payout_amount',
            'currency', 'stripe_account_id', 'stripe_onboarding_complete',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'teacher', 'total_earned', 'pending_payout', 'available_for_payout',
            'lifetime_payout', 'last_payout_at', 'last_payout_amount',
            'stripe_onboarding_complete', 'created_at', 'updated_at'
        ]


class TransactionSerializer(UnifiedTransactionSerializer):
    """Wrapper for unified TransactionSerializer with earning-specific additions"""
    
    class Meta(UnifiedTransactionSerializer.Meta):
        fields = UnifiedTransactionSerializer.Meta.fields + [
            'teacher_amount', 'enrollment', 'order',
        ]


class TransactionListSerializer(UnifiedTransactionListSerializer):
    """Wrapper for unified TransactionListSerializer"""
    pass


class PayoutSerializer(serializers.ModelSerializer):
    transaction_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id', 'amount', 'net_amount', 'fee', 'currency',
            'status', 'method', 'stripe_payout_id', 'bank_transfer_id',
            'period_start', 'period_end', 'transaction_count',
            'failure_reason', 'retry_count',
            'requested_at', 'processed_at', 'paid_at'
        ]
        read_only_fields = [
            'id', 'amount', 'net_amount', 'fee', 'currency',
            'status', 'method', 'stripe_payout_id', 'bank_transfer_id',
            'period_start', 'period_end', 'failure_reason', 'retry_count',
            'requested_at', 'processed_at', 'paid_at'
        ]


class PayoutDetailSerializer(PayoutSerializer):
    transactions = UnifiedTransactionListSerializer(many=True, read_only=True)

    class Meta(PayoutSerializer.Meta):
        fields = PayoutSerializer.Meta.fields + ['transactions']


class PayoutRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    method = serializers.ChoiceField(choices=Payout.Method.choices, default=Payout.Method.STRIPE)

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


class PayoutScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutSchedule
        fields = [
            'schedule', 'day_of_week', 'day_of_month',
            'minimum_amount', 'auto_payout', 'timezone',
            'last_run_at', 'next_run_at'
        ]
        read_only_fields = ['last_run_at', 'next_run_at']


class PayoutScheduleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutSchedule
        fields = [
            'schedule', 'day_of_week', 'day_of_month',
            'minimum_amount', 'auto_payout', 'timezone'
        ]

    def validate(self, attrs):
        schedule = attrs.get('schedule')
        day_of_week = attrs.get('day_of_week')
        day_of_month = attrs.get('day_of_month')

        if schedule == 'weekly' and day_of_week is None:
            raise serializers.ValidationError({"day_of_week": "Required for weekly schedule."})
        if schedule == 'monthly' and day_of_month is None:
            raise serializers.ValidationError({"day_of_month": "Required for monthly schedule."})
        if schedule == 'biweekly' and day_of_week is None:
            raise serializers.ValidationError({"day_of_week": "Required for biweekly schedule."})
        if day_of_month is not None and (day_of_month < 1 or day_of_month > 28):
            raise serializers.ValidationError({"day_of_month": "Must be between 1 and 28."})

        return attrs


class RevenueReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueReport
        fields = [
            'id', 'period_start', 'period_end',
            'gross_revenue', 'platform_fees', 'net_revenue', 'refunds', 'payouts',
            'courses_count', 'sales_count', 'students_count',
            'report_data', 'generated_at'
        ]
        read_only_fields = fields


class EarningsSummarySerializer(serializers.Serializer):
    total_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_payout = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_for_payout = serializers.DecimalField(max_digits=12, decimal_places=2)
    lifetime_payout = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_payout_at = serializers.DateTimeField(allow_null=True)
    last_payout_amount = serializers.DecimalField(max_digits=12, decimal_places=2)

    this_month_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_month_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    this_month_sales = serializers.IntegerField()
    last_month_sales = serializers.IntegerField()

    stripe_onboarding_complete = serializers.BooleanField()
    payout_schedule = serializers.DictField()