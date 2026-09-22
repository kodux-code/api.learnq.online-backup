from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action

from .models import TeacherEarning, Payout, PayoutSchedule, RevenueReport
from .serializers import (
    TeacherEarningSerializer, TransactionSerializer, TransactionListSerializer,
    PayoutSerializer, PayoutDetailSerializer, PayoutRequestSerializer,
    PayoutScheduleSerializer, PayoutScheduleUpdateSerializer,
    RevenueReportSerializer, EarningsSummarySerializer
)
from client.permissions import IsAccountOwnerOrStaff

# Use unified transaction model
from transaction.models import Transaction


class TeacherEarningView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = TeacherEarningSerializer

    def get_object(self):
        earning, _ = TeacherEarning.objects.get_or_create(teacher=self.request.user)
        return earning


class EarningsSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]

    def get(self, request):
        earning, _ = TeacherEarning.objects.get_or_create(teacher=request.user)
        schedule, _ = PayoutSchedule.objects.get_or_create(teacher=request.user)

        now = timezone.now()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = this_month_start - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        this_month = Transaction.objects.filter(
            teacher=request.user,
            transaction_type=Transaction.Type.COURSE_SALE,
            status=Transaction.Status.COMPLETED,
            completed_at__gte=this_month_start
        ).aggregate(total=Sum('teacher_amount'), count=Count('id'))

        last_month = Transaction.objects.filter(
            teacher=request.user,
            transaction_type=Transaction.Type.COURSE_SALE,
            status=Transaction.Status.COMPLETED,
            completed_at__gte=last_month_start,
            completed_at__lt=this_month_start
        ).aggregate(total=Sum('teacher_amount'), count=Count('id'))

        data = {
            'total_earned': earning.total_earned,
            'pending_payout': earning.pending_payout,
            'available_for_payout': earning.available_for_payout,
            'lifetime_payout': earning.lifetime_payout,
            'last_payout_at': earning.last_payout_at,
            'last_payout_amount': earning.last_payout_amount,
            'this_month_earnings': this_month['total'] or 0,
            'last_month_earnings': last_month['total'] or 0,
            'this_month_sales': this_month['count'] or 0,
            'last_month_sales': last_month['count'] or 0,
            'stripe_onboarding_complete': earning.stripe_onboarding_complete,
            'payout_schedule': PayoutScheduleSerializer(schedule).data
        }
        serializer = EarningsSummarySerializer(data)
        return Response(serializer.data)


class TransactionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = TransactionListSerializer

    def get_queryset(self):
        queryset = Transaction.objects.filter(teacher=self.request.user).select_related('course')

        # Filters
        type_filter = self.request.query_params.get('type')
        if type_filter:
            queryset = queryset.filter(transaction_type=type_filter)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        # Date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        return queryset


class TransactionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = TransactionSerializer
    queryset = Transaction.objects.select_related('course', 'enrollment__student')

    def get_queryset(self):
        return Transaction.objects.filter(teacher=self.request.user)


class PayoutListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = PayoutSerializer

    def get_queryset(self):
        return Payout.objects.filter(teacher=self.request.user).prefetch_related('transactions')


class PayoutDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = PayoutDetailSerializer
    queryset = Payout.objects.prefetch_related('transactions__course')

    def get_queryset(self):
        return Payout.objects.filter(teacher=self.request.user)


class PayoutRequestView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = PayoutRequestSerializer

    def post(self, request, *args, **kwargs):
        earning, _ = TeacherEarning.objects.get_or_create(teacher=request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data.get('amount') or earning.available_for_payout
        method = serializer.validated_data.get('method')

        if amount > earning.available_for_payout:
            return Response(
                {'error': f'Insufficient available balance. Available: ${earning.available_for_payout}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if amount < 1:
            return Response(
                {'error': 'Minimum payout amount is $1.00'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate fee (example: 1% + $0.25 for Stripe)
        fee = round(amount * 0.01 + 0.25, 2)
        net_amount = amount - fee

        payout = Payout.objects.create(
            teacher=request.user,
            earning=earning,
            amount=amount,
            net_amount=net_amount,
            fee=fee,
            currency=earning.currency,
            method=method,
            period_start=timezone.now() - timedelta(days=30),
            period_end=timezone.now()
        )

        # In production, integrate with Stripe here
        # For now, mark as pending
        return Response(PayoutDetailSerializer(payout).data, status=status.HTTP_201_CREATED)


class PayoutScheduleView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return PayoutScheduleUpdateSerializer
        return PayoutScheduleSerializer

    def get_object(self):
        schedule, _ = PayoutSchedule.objects.get_or_create(teacher=self.request.user)
        return schedule


class RevenueReportListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = RevenueReportSerializer

    def get_queryset(self):
        return RevenueReport.objects.filter(teacher=self.request.user)


class RevenueReportDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = RevenueReportSerializer
    queryset = RevenueReport.objects.all()

    def get_queryset(self):
        return RevenueReport.objects.filter(teacher=self.request.user)


class RevenueReportGenerateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]

    def post(self, request):
        period_start = request.data.get('period_start')
        period_end = request.data.get('period_end')

        if not period_start or not period_end:
            return Response(
                {'error': 'period_start and period_end are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            period_start = timezone.datetime.fromisoformat(period_start.replace('Z', '+00:00'))
            period_end = timezone.datetime.fromisoformat(period_end.replace('Z', '+00:00'))
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use ISO format.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if period_start >= period_end:
            return Response(
                {'error': 'period_start must be before period_end'},
                status=status.HTTP_400_BAD_REQUEST
            )

        report, created = RevenueReport.objects.get_or_create(
            teacher=request.user,
            period_start=period_start,
            period_end=period_end,
            defaults={}
        )

        if not created:
            # Recalculate
            pass

        self._calculate_report(report)

        return Response(RevenueReportSerializer(report).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def _calculate_report(self, report):
        transactions = Transaction.objects.filter(
            teacher=report.teacher,
            completed_at__gte=report.period_start,
            completed_at__lte=report.period_end,
            status=Transaction.Status.COMPLETED
        )

        sales = transactions.filter(transaction_type=Transaction.Type.COURSE_SALE)
        refunds = transactions.filter(transaction_type=Transaction.Type.REFUND)
        payouts = transactions.filter(transaction_type=Transaction.Type.TEACHER_PAYOUT)

        report.gross_revenue = sales.aggregate(total=Sum('amount'))['total'] or 0
        report.platform_fees = sales.aggregate(total=Sum('platform_fee'))['total'] or 0
        report.net_revenue = sales.aggregate(total=Sum('teacher_amount'))['total'] or 0
        report.refunds = abs(refunds.aggregate(total=Sum('amount'))['total'] or 0)
        report.payouts = abs(payouts.aggregate(total=Sum('amount'))['total'] or 0)

        report.courses_count = sales.values('course').distinct().count()
        report.sales_count = sales.count()
        report.students_count = sales.values('enrollment__student').distinct().count()

        report.report_data = {
            'by_course': list(sales.values('course__title').annotate(
                sales=Count('id'),
                revenue=Sum('teacher_amount')
            ).order_by('-revenue')),
            'by_type': list(transactions.values('transaction_type').annotate(
                count=Count('id'),
                total=Sum('amount')
            )),
        }
        report.save()


# Admin/Staff views
class AdminEarningsOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        stats = TeacherEarning.objects.aggregate(
            total_teachers=Count('id'),
            total_earned=Sum('total_earned'),
            total_pending=Sum('pending_payout'),
            total_paid_out=Sum('lifetime_payout'),
            stripe_onboarded=Count('id', filter=Q(stripe_onboarding_complete=True)),
        )

        recent_payouts = Payout.objects.filter(
            status=Payout.Status.PAID
        ).select_related('teacher').order_by('-paid_at')[:10]

        pending_payouts = Payout.objects.filter(
            status=Payout.Status.PENDING
        ).count()

        failed_payouts = Payout.objects.filter(
            status=Payout.Status.FAILED
        ).count()

        return Response({
            'overview': stats,
            'recent_payouts': PayoutSerializer(recent_payouts, many=True).data,
            'pending_payouts_count': pending_payouts,
            'failed_payouts_count': failed_payouts,
        })


class AdminPayoutManagementView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PayoutDetailSerializer

    def get_queryset(self):
        queryset = Payout.objects.select_related('teacher', 'earning').prefetch_related('transactions')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset


class AdminPayoutActionView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        action = request.data.get('action')
        payout = Payout.objects.get(pk=pk)

        if action == 'process':
            payout.mark_processing()
            # TODO: Call Stripe API
            return Response({'detail': 'Payout marked as processing.'})

        elif action == 'complete':
            payout.mark_paid()
            return Response({'detail': 'Payout marked as paid.'})

        elif action == 'fail':
            reason = request.data.get('reason', 'Manual failure')
            payout.mark_failed(reason)
            return Response({'detail': 'Payout marked as failed.'})

        elif action == 'cancel':
            if payout.status in [Payout.Status.PAID, Payout.Status.PROCESSING]:
                return Response({'error': 'Cannot cancel completed/processing payout.'}, status=status.HTTP_400_BAD_REQUEST)
            payout.status = Payout.Status.CANCELLED
            payout.save()
            return Response({'detail': 'Payout cancelled.'})

        return Response({'error': 'Invalid action.'}, status=status.HTTP_400_BAD_REQUEST)