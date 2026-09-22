from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import action
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404

from .models import Transaction, Wallet, WalletTransaction
from .serializers import (
    TransactionSerializer, TransactionListSerializer, TransactionCreateSerializer,
    TransactionUpdateSerializer, WalletSerializer, WalletTransactionSerializer,
    WalletTopUpSerializer, TransactionStatsSerializer
)
from client.permissions import IsAccountOwnerOrStaff
from course.models import Course, Enrollment


class TransactionViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['gateway_transaction_id', 'description', 'user__display_name', 'teacher__display_name']
    ordering_fields = ['created_at', 'amount', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Transaction.objects.select_related('user', 'teacher', 'course', 'coupon', 'payout')
        return Transaction.objects.filter(
            Q(user=user) | Q(teacher=user)
        ).select_related('user', 'teacher', 'course', 'coupon', 'payout')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TransactionCreateSerializer
        if self.action in ['update', 'partial_update']:
            return TransactionUpdateSerializer
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Filters
        direction = request.query_params.get('direction')
        if direction:
            queryset = queryset.filter(direction=direction)
        
        transaction_type = request.query_params.get('type')
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        course_id = request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        teacher_id = request.query_params.get('teacher')
        if teacher_id:
            queryset = queryset.filter(teacher_id=teacher_id)
        
        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_completed(self, request, *args, **kwargs):
        transaction = self.get_object()
        transaction.mark_completed()
        return Response(TransactionSerializer(transaction).data)
    
    @action(detail=True, methods=['post'])
    def mark_failed(self, request, *args, **kwargs):
        transaction = self.get_object()
        reason = request.data.get('reason', '')
        transaction.mark_failed(reason)
        return Response(TransactionSerializer(transaction).data)
    
    @action(detail=True, methods=['post'])
    def reverse(self, request, *args, **kwargs):
        transaction = self.get_object()
        transaction.mark_reversed()
        return Response(TransactionSerializer(transaction).data)
    
    @action(detail=False, methods=['get'])
    def my_earnings(self, request, *args, **kwargs):
        """Get earnings for the current user as teacher."""
        user = request.user
        if user.role != user.Role.TEACHER:
            return Response({'error': 'Only teachers can view earnings.'}, status=status.HTTP_403_FORBIDDEN)
        
        queryset = Transaction.objects.filter(
            teacher=user,
            direction='outgoing',
            transaction_type='teacher_payout'
        ).order_by('-created_at')
        
        page = self.paginate_queryset(queryset)
        serializer = TransactionListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_purchases(self, request, *args, **kwargs):
        """Get purchases for the current user as student."""
        queryset = Transaction.objects.filter(
            user=request.user,
            direction='incoming',
            status=Transaction.Status.COMPLETED
        ).order_by('-created_at')
        
        page = self.paginate_queryset(queryset)
        serializer = TransactionListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)


class WalletView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletSerializer
    
    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet


class WalletTransactionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletTransactionSerializer
    
    def get_queryset(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet.wallet_transactions.all()


class WalletTopUpView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = WalletTopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        amount = serializer.validated_data['amount']
        gateway = serializer.validated_data['gateway']
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # Create transaction for top-up
        transaction = Transaction.objects.create(
            user=request.user,
            direction='incoming',
            transaction_type='donation',  # Using donation as top-up type
            status=Transaction.Status.COMPLETED,
            amount=amount,
            net_amount=amount,
            platform_fee=0,
            currency='USD',
            gateway=gateway,
            description=f'Wallet top-up via {gateway}',
            completed_at=timezone.now()
        )
        
        wallet.add_funds(amount, description=f'Top-up via {gateway}', reference_id=str(transaction.id), reference_type='transaction')
        
        return Response({
            'balance': wallet.balance,
            'transaction_id': str(transaction.id)
        })


class TransactionStatsView(APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (start_of_month - timedelta(days=1)).replace(day=1)
        
        # Revenue (incoming completed)
        revenue_agg = Transaction.objects.filter(
            direction='incoming',
            status=Transaction.Status.COMPLETED
        ).aggregate(
            total=Sum('amount'),
            net=Sum('net_amount'),
            fees=Sum('platform_fee'),
            count=Count('id')
        )
        
        # Payouts (outgoing completed)
        payout_agg = Transaction.objects.filter(
            direction='outgoing',
            status=Transaction.Status.COMPLETED,
            transaction_type='teacher_payout'
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # This month revenue
        this_month_revenue = Transaction.objects.filter(
            direction='incoming',
            status=Transaction.Status.COMPLETED,
            completed_at__gte=start_of_month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Last month revenue
        last_month_revenue = Transaction.objects.filter(
            direction='incoming',
            status=Transaction.Status.COMPLETED,
            completed_at__gte=last_month_start,
            completed_at__lt=start_of_month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # By type
        by_type = dict(
            Transaction.objects.filter(status=Transaction.Status.COMPLETED)
            .values('transaction_type')
            .annotate(
                count=Count('id'),
                total=Sum('amount'),
                net=Sum('net_amount')
            )
            .values_list('transaction_type', 'total')
        )
        
        # By status
        by_status = dict(
            Transaction.objects.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        # By month (last 12 months)
        by_month = list(
            Transaction.objects.filter(
                status=Transaction.Status.COMPLETED,
                completed_at__gte=now - timedelta(days=365)
            )
            .annotate(month=TruncMonth('completed_at'))
            .values('month')
            .annotate(
                revenue=Sum('amount', filter=Q(direction='incoming')),
                payouts=Sum('amount', filter=Q(direction='outgoing', transaction_type='teacher_payout')),
                count=Count('id')
            )
            .order_by('month')
        )
        
        stats = {
            'total_revenue': revenue_agg['total'] or 0,
            'total_net_revenue': revenue_agg['net'] or 0,
            'total_fees': revenue_agg['fees'] or 0,
            'total_payouts': payout_agg['total'] or 0,
            'transaction_count': revenue_agg['count'] or 0,
            'payout_count': payout_agg['count'] or 0,
            'this_month_revenue': this_month_revenue,
            'last_month_revenue': last_month_revenue,
            'by_type': by_type,
            'by_status': by_status,
            'by_month': by_month,
        }
        
        return Response(TransactionStatsSerializer(stats).data)


class TeacherEarningsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        if user.role != user.Role.TEACHER:
            return Response({'error': 'Only teachers can view earnings.'}, status=status.HTTP_403_FORBIDDEN)
        
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (start_of_month - timedelta(days=1)).replace(day=1)
        
        earnings = Transaction.objects.filter(
            teacher=user,
            direction='incoming',
            status=Transaction.Status.COMPLETED
        ).aggregate(
            total_earned=Sum('teacher_amount'),
            this_month=Sum('teacher_amount', filter=Q(completed_at__gte=start_of_month)),
            last_month=Sum('teacher_amount', filter=Q(completed_at__gte=last_month_start, completed_at__lt=start_of_month)),
            count=Count('id')
        )
        
        # Pending payouts
        pending = Transaction.objects.filter(
            teacher=user,
            direction='outgoing',
            transaction_type='teacher_payout',
            status__in=[Transaction.Status.PENDING, Transaction.Status.PROCESSING]
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Paid out
        paid_out = Transaction.objects.filter(
            teacher=user,
            direction='outgoing',
            transaction_type='teacher_payout',
            status=Transaction.Status.COMPLETED
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # By course
        by_course = list(
            Transaction.objects.filter(
                teacher=user,
                direction='incoming',
                status=Transaction.Status.COMPLETED
            )
            .values('course__title', 'course__id')
            .annotate(
                sales=Count('id'),
                earned=Sum('teacher_amount')
            )
            .order_by('-earned')
        )
        
        return Response({
            'total_earned': earnings['total_earned'] or 0,
            'this_month_earnings': earnings['this_month'] or 0,
            'last_month_earnings': earnings['last_month'] or 0,
            'total_sales': earnings['count'] or 0,
            'pending_payout': pending,
            'total_paid_out': paid_out,
            'available_for_payout': (earnings['total_earned'] or 0) - paid_out,
            'by_course': by_course,
        })