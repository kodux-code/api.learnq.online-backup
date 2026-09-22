from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework import serializers
from datetime import timedelta
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib.auth import get_user_model

from .models import (
    Bundle, Coupon,
    SubscriptionPlan, Subscription, SubscriptionInvoice,
    Refund, WebhookEvent
)
from payment.serializers import (
    SubscriptionInvoiceSerializer,
    RefundSerializer
)
from client.permissions import IsAccountOwnerOrStaff
from course.models import Course, Enrollment, CourseTeacher

# Use unified transaction model
from transaction.models import Transaction
from transaction.serializers import TransactionSerializer as UnifiedTransactionSerializer

User = get_user_model()


class OrderViewSet(generics.GenericAPIView):
    """Legacy OrderViewSet - use transaction.Transaction API instead.
    This is kept for backwards compatibility but creates unified transactions internally."""
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'total_amount', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        # Return unified transactions for this user
        return Transaction.objects.filter(user=self.request.user).select_related('course', 'coupon')

    def get_serializer_class(self):
        from .serializers import OrderSerializer, OrderCreateSerializer, OrderPreviewSerializer
        if self.action == 'create':
            return OrderCreateSerializer
        if self.action == 'preview':
            return OrderPreviewSerializer
        return OrderSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

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

        with transaction.atomic():
            txn = self._create_unified_transaction(request.user, serializer.validated_data)

        return Response({
            'transaction': UnifiedTransactionSerializer(txn).data,
            'message': 'Order created as unified transaction'
        }, status=status.HTTP_201_CREATED)

    def _create_unified_transaction(self, user, data):
        items_data = data['items']
        coupon_code = data.get('coupon_code', '').strip().upper()
        gateway = data['gateway']
        billing_email = data['billing_email']

        # Calculate prices
        order_items = []
        subtotal = 0

        for item_data in items_data:
            item_type = item_data['type']
            item_id = item_data['id']
            quantity = item_data.get('quantity', 1)

            if item_type == 'course':
                course = get_object_or_404(Course, id=item_id, status=Course.Status.PUBLISHED)
                if Enrollment.objects.filter(student=user, course=course, status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]).exists():
                    raise serializers.ValidationError(f"Already enrolled in {course.title}")

                price = course.current_price
                teacher = course.course_teachers.filter(role=CourseTeacher.Role.PRIMARY, is_active=True).first()
                teacher_user = teacher.teacher if teacher else None
                revenue_share = float(teacher.revenue_share) if teacher else 0

                order_items.append({
                    'type': 'course',
                    'course': course,
                    'name': course.title,
                    'unit_price': price,
                    'quantity': quantity,
                    'total_price': price * quantity,
                    'teacher': teacher_user,
                    'revenue_share_percent': revenue_share,
                    'teacher_amount': price * quantity * (revenue_share / 100)
                })
                subtotal += price * quantity

            elif item_type == 'bundle':
                bundle = get_object_or_404(Bundle, id=item_id, is_active=True)
                if bundle.valid_from and timezone.now() < bundle.valid_from:
                    raise serializers.ValidationError(f"Bundle {bundle.title} is not yet available.")
                if bundle.valid_until and timezone.now() > bundle.valid_until:
                    raise serializers.ValidationError(f"Bundle {bundle.title} has expired.")

                price = bundle.sale_price
                order_items.append({
                    'type': 'bundle',
                    'bundle': bundle,
                    'name': bundle.title,
                    'unit_price': price,
                    'quantity': quantity,
                    'total_price': price * quantity,
                    'teacher': None,
                    'revenue_share_percent': 0,
                    'teacher_amount': 0
                })
                subtotal += price * quantity

        # Apply coupon
        discount = 0
        coupon = None
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code)
                valid, msg = coupon.is_valid(user, subtotal)
                if not valid:
                    raise serializers.ValidationError(msg)
                discount = coupon.calculate_discount(subtotal)
            except Coupon.DoesNotExist:
                raise serializers.ValidationError("Invalid coupon code.")

        tax = 0  # Calculate based on billing country
        total = subtotal - discount + tax

        # Create unified transaction
        txn = Transaction.objects.create(
            user=user,
            direction=Transaction.Direction.INCOMING,
            transaction_type=Transaction.Type.COURSE_SALE if all(i['type'] == 'course' for i in order_items) else Transaction.Type.BUNDLE_SALE,
            status=Transaction.Status.PENDING,
            amount=total,
            net_amount=total,
            platform_fee=0,
            currency='USD',
            gateway=gateway,
            billing_email=billing_email,
            billing_name=data.get('billing_name', ''),
            billing_address=data.get('billing_address', {}),
            billing_country=data.get('billing_country', ''),
            items=[{
                'type': i['type'],
                'id': str(i.get('course') or i.get('bundle')).id if i.get('course') or i.get('bundle') else None,
                'name': i['name'],
                'unit_price': str(i['unit_price']),
                'quantity': i['quantity'],
                'total_price': str(i['total_price'])
            } for i in order_items],
            metadata=data.get('metadata', {}),
            expires_at=timezone.now() + timedelta(minutes=30)
        )

        if coupon:
            txn.coupon = coupon
            txn.coupon_code = coupon_code
            txn.discount_amount = discount
            txn.save(update_fields=['coupon', 'coupon_code', 'discount_amount'])

        # Create enrollment(s) if payment completes later via webhook
        # For now, just create the transaction
        return txn

    @action(detail=False, methods=['post'])
    def preview(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        items_data = serializer.validated_data['items']
        coupon_code = serializer.validated_data.get('coupon_code', '').strip().upper()

        subtotal = 0
        preview_items = []

        for item_data in items_data:
            item_type = item_data['type']
            item_id = item_data['id']
            quantity = item_data.get('quantity', 1)

            if item_type == 'course':
                course = get_object_or_404(Course, id=item_id, status=Course.Status.PUBLISHED)
                price = course.current_price
                subtotal += price * quantity
                preview_items.append({
                    'type': 'course',
                    'course': course,
                    'name': course.title,
                    'unit_price': price,
                    'quantity': quantity,
                    'total_price': price * quantity,
                    'teacher': None,
                    'revenue_share_percent': 0,
                    'teacher_amount': 0
                })
            elif item_type == 'bundle':
                bundle = get_object_or_404(Bundle, id=item_id, is_active=True)
                price = bundle.sale_price
                subtotal += price * quantity
                preview_items.append({
                    'type': 'bundle',
                    'bundle': bundle,
                    'name': bundle.title,
                    'unit_price': price,
                    'quantity': quantity,
                    'total_price': price * quantity,
                    'teacher': None,
                    'revenue_share_percent': 0,
                    'teacher_amount': 0
                })

        discount = 0
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code)
                valid, _ = coupon.is_valid(user, subtotal)
                if valid:
                    discount = coupon.calculate_discount(subtotal)
            except Coupon.DoesNotExist:
                pass

        tax = 0
        total = subtotal - discount + tax

        return Response({
            'items': preview_items,
            'subtotal': subtotal,
            'tax_amount': tax,
            'discount_amount': discount,
            'total_amount': total,
            'currency': 'USD',
            'coupon': {'code': coupon_code} if discount > 0 else None
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel(self, request, *args, **kwargs):
        txn = self.get_object()
        if txn.status not in [Transaction.Status.PENDING, Transaction.Status.PROCESSING]:
            return Response({'error': 'Order cannot be cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        txn.status = Transaction.Status.CANCELLED
        txn.cancelled_at = timezone.now()
        txn.save(update_fields=['status', 'cancelled_at', 'updated_at'])
        return Response({'detail': 'Order cancelled.'})


class OrderWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, gateway):
        payload = request.data
        event_id = request.headers.get('Stripe-Event-Id') or request.headers.get('X-PayPal-Event-Id')

        webhook = WebhookEvent.objects.create(
            gateway=gateway,
            event_type=payload.get('type', 'unknown'),
            event_id=event_id or '',
            payload=payload
        )

        if gateway == 'stripe':
            self._process_stripe_webhook(webhook, payload)
        elif gateway == 'paypal':
            self._process_paypal_webhook(webhook, payload)

        return Response({'received': True})

    def _process_stripe_webhook(self, webhook, payload):
        event_type = payload.get('type')

        if event_type == 'checkout.session.completed':
            session = payload['data']['object']
            self._handle_checkout_completed(session)
        elif event_type == 'payment_intent.succeeded':
            intent = payload['data']['object']
            self._handle_payment_succeeded(intent)
        elif event_type == 'payment_intent.payment_failed':
            intent = payload['data']['object']
            self._handle_payment_failed(intent)
        elif event_type == 'invoice.payment_succeeded':
            invoice = payload['data']['object']
            self._handle_subscription_payment(invoice)
        elif event_type == 'customer.subscription.updated':
            sub = payload['data']['object']
            self._handle_subscription_updated(sub)
        elif event_type == 'customer.subscription.deleted':
            sub = payload['data']['object']
            self._handle_subscription_cancelled(sub)

        webhook.mark_processed()

    def _process_paypal_webhook(self, webhook, payload):
        webhook.mark_processed()

    def _handle_checkout_completed(self, session):
        order_number = session.get('metadata', {}).get('order_number')
        if not order_number:
            return

        # Find transaction by gateway_order_id
        try:
            txn = Transaction.objects.get(gateway_order_id=session.get('id'))
        except Transaction.DoesNotExist:
            return

        if txn.status == Transaction.Status.COMPLETED:
            return

        txn.gateway_payment_id = session.get('payment_intent')
        txn.gateway_response = session
        txn.status = Transaction.Status.COMPLETED
        txn.completed_at = timezone.now()
        txn.save(update_fields=['status', 'completed_at', 'gateway_payment_id', 'gateway_response', 'updated_at'])

        self._create_enrollments(txn)

    def _handle_payment_succeeded(self, intent):
        order_number = intent.get('metadata', {}).get('order_number')
        if not order_number:
            return

        try:
            txn = Transaction.objects.get(gateway_order_id=intent.get('metadata', {}).get('order_number'))
        except Transaction.DoesNotExist:
            return

        if txn.status == Transaction.Status.COMPLETED:
            return

        txn.gateway_payment_id = intent['id']
        txn.gateway_response = intent
        txn.status = Transaction.Status.COMPLETED
        txn.completed_at = timezone.now()
        txn.save(update_fields=['status', 'completed_at', 'gateway_payment_id', 'gateway_response', 'updated_at'])
        self._create_enrollments(txn)

    def _handle_payment_failed(self, intent):
        order_number = intent.get('metadata', {}).get('order_number')
        if not order_number:
            return

        try:
            txn = Transaction.objects.get(gateway_order_id=order_number)
        except Transaction.DoesNotExist:
            return

        txn.status = Transaction.Status.FAILED
        txn.failed_at = timezone.now()
        txn.gateway_response = intent
        txn.metadata['failure_reason'] = intent.get('last_payment_error', {}).get('message', 'Payment failed')
        txn.save(update_fields=['status', 'failed_at', 'gateway_response', 'metadata', 'updated_at'])

    def _handle_subscription_payment(self, invoice):
        stripe_sub_id = invoice.get('subscription')
        if not stripe_sub_id:
            return

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=stripe_sub_id)
        except Subscription.DoesNotExist:
            return

        SubscriptionInvoice.objects.update_or_create(
            stripe_invoice_id=invoice['id'],
            defaults={
                'subscription': subscription,
                'amount': invoice['amount_paid'] / 100,
                'currency': invoice['currency'].upper(),
                'status': 'paid' if invoice['status'] == 'paid' else 'open',
                'period_start': timezone.datetime.fromtimestamp(invoice['period_start'], tz=timezone.utc),
                'period_end': timezone.datetime.fromtimestamp(invoice['period_end'], tz=timezone.utc),
                'paid_at': timezone.now() if invoice['status'] == 'paid' else None
            }
        )

    def _handle_subscription_updated(self, sub):
        try:
            subscription = Subscription.objects.get(stripe_subscription_id=sub['id'])
        except Subscription.DoesNotExist:
            return

        subscription.status = sub['status']
        subscription.current_period_start = timezone.datetime.fromtimestamp(sub['current_period_start'], tz=timezone.utc)
        subscription.current_period_end = timezone.datetime.fromtimestamp(sub['current_period_end'], tz=timezone.utc)
        subscription.cancel_at_period_end = sub.get('cancel_at_period_end', False)
        subscription.save()

    def _handle_subscription_cancelled(self, sub):
        try:
            subscription = Subscription.objects.get(stripe_subscription_id=sub['id'])
        except Subscription.DoesNotExist:
            return

        subscription.status = Subscription.Status.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.ended_at = timezone.datetime.fromtimestamp(sub['current_period_end'], tz=timezone.utc)
        subscription.save()

    def _create_enrollments(self, txn):
        # Parse items from transaction metadata
        items = txn.items or []
        for item in items:
            if item.get('type') == 'course':
                course_id = item.get('id')
                try:
                    course = Course.objects.get(id=course_id)
                except Course.DoesNotExist:
                    continue

                enrollment, created = Enrollment.objects.get_or_create(
                    student=txn.user,
                    course=course,
                    defaults={
                        'status': Enrollment.Status.ACTIVE,
                        'amount_paid': txn.net_amount,
                        'currency': txn.currency,
                        'payment_id': txn.gateway_payment_id or txn.gateway_order_id
                    }
                )
                if created:
                    course.total_students = F('total_students') + 1
                    course.save(update_fields=['total_students'])


class BundleViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'sale_price']
    ordering = ['-is_featured', '-created_at']

    def get_queryset(self):
        now = timezone.now()
        return Bundle.objects.filter(
            is_active=True
        ).filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now)
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=now)
        ).prefetch_related('courses')

    def get_serializer_class(self):
        from .serializers import BundleSerializer, BundleCreateSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return BundleCreateSerializer
        return BundleSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
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

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CouponViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        now = timezone.now()
        return Coupon.objects.filter(
            is_active=True,
            valid_from__lte=now,
            valid_until__gte=now
        )

    def get_serializer_class(self):
        from .serializers import CouponSerializer, CouponCreateSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return CouponCreateSerializer
        return CouponSerializer

    def get_permissions(self):
        if self.action in ['list', 'create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def validate(self, request, *args, **kwargs):
        from .serializers import CouponValidateSerializer, CouponValidateResponseSerializer
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data['code'].upper()
        order_amount = serializer.validated_data['order_amount']
        items = serializer.validated_data.get('items', [])

        try:
            coupon = Coupon.objects.get(code=code)
        except Coupon.DoesNotExist:
            return Response({'valid': False, 'message': 'Invalid coupon code.', 'discount_amount': 0})

        valid, message = coupon.is_valid(request.user, order_amount, items)
        discount = coupon.calculate_discount(order_amount, items) if valid else 0

        return Response({
            'valid': valid,
            'message': message,
            'discount_amount': discount
        })


class SubscriptionPlanViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)

    def get_serializer_class(self):
        from .serializers import SubscriptionPlanSerializer, SubscriptionPlanCreateSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return SubscriptionPlanCreateSerializer
        return SubscriptionPlanSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class SubscriptionViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user).select_related('plan')

    def get_serializer_class(self):
        from .serializers import SubscriptionSerializer, SubscriptionCreateSerializer
        if self.action == 'create':
            return SubscriptionCreateSerializer
        return SubscriptionSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        from .serializers import SubscriptionCreateSerializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = get_object_or_404(SubscriptionPlan, id=serializer.validated_data['plan_id'], is_active=True)

        subscription = Subscription.objects.create(
            user=request.user,
            plan=plan,
            status=Subscription.Status.TRIALING if plan.trial_days > 0 else Subscription.Status.ACTIVE,
            price=plan.price,
            currency=plan.currency,
            interval=plan.interval,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30 * plan.interval_count),
            trial_end=timezone.now() + timedelta(days=plan.trial_days) if plan.trial_days > 0 else None,
            stripe_customer_id='',
            stripe_subscription_id=''
        )

        return Response(subscription_serializer(subscription).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, *args, **kwargs):
        subscription = self.get_object()
        cancel_immediately = request.data.get('immediately', False)

        if cancel_immediately:
            subscription.status = Subscription.Status.CANCELLED
            subscription.ended_at = timezone.now()
        else:
            subscription.cancel_at_period_end = True
            subscription.cancellation_reason = request.data.get('reason', '')

        subscription.save()
        return Response(subscription_serializer(subscription).data)

    @action(detail=True, methods=['post'])
    def resume(self, request, *args, **kwargs):
        subscription = self.get_object()

        if subscription.status != Subscription.Status.CANCELLED:
            return Response({'error': 'Subscription is not cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        subscription.status = Subscription.Status.ACTIVE
        subscription.cancel_at_period_end = False
        subscription.cancellation_reason = ''
        subscription.save()
        return Response(subscription_serializer(subscription).data)

    @action(detail=True, methods=['get'])
    def invoices(self, request, *args, **kwargs):
        subscription = self.get_object()
        invoices = subscription.invoices.all()
        serializer = SubscriptionInvoiceSerializer(invoices, many=True)
        return Response(serializer.data)


def subscription_serializer(subscription):
    from .serializers import SubscriptionSerializer
    return SubscriptionSerializer(subscription).data


class RefundViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Refund.objects.filter(user=self.request.user).select_related('transaction')

    def get_serializer_class(self):
        from .serializers import RefundSerializer, RefundRequestSerializer
        if self.action == 'create':
            return RefundRequestSerializer
        return RefundSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        from .serializers import RefundRequestSerializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        txn = get_object_or_404(Transaction, id=serializer.validated_data['transaction_id'], user=request.user)

        if txn.status != Transaction.Status.COMPLETED:
            return Response({'error': 'Transaction cannot be refunded.'}, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data.get('amount') or txn.amount

        if amount > txn.amount:
            return Response({'error': 'Refund amount exceeds transaction total.'}, status=status.HTTP_400_BAD_REQUEST)

        refund = Refund.objects.create(
            transaction=txn,
            user=request.user,
            amount=amount,
            reason=serializer.validated_data['reason'],
            reason_details=serializer.validated_data.get('reason_details', ''),
            requested_by=request.user
        )

        return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


class AdminRefundViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Refund.objects.select_related('transaction', 'user', 'approved_by')

    def get_serializer_class(self):
        from .serializers import RefundSerializer, RefundActionSerializer
        if self.action == 'action':
            return RefundActionSerializer
        return RefundSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    @action(detail=True, methods=['post'])
    def action(self, request, *args, **kwargs):
        refund = self.get_object()
        from .serializers import RefundActionSerializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']

        if action == 'approve':
            refund.approve(request.user)
        elif action == 'reject':
            refund.status = Refund.Status.REJECTED
            refund.save()
        elif action == 'process':
            refund.process()
            refund.complete()
        elif action == 'cancel':
            if refund.status in [Refund.Status.COMPLETED, Refund.Status.PROCESSING]:
                return Response({'error': 'Cannot cancel completed/processing refund.'}, status=status.HTTP_400_BAD_REQUEST)
            refund.status = Refund.Status.CANCELLED
            refund.save()
        else:
            return Response({'error': 'Invalid action.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(RefundSerializer(refund).data)


class PaymentStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (start_of_month - timedelta(days=1)).replace(day=1)

        stats = {
            'total_revenue': Transaction.objects.filter(
                direction=Transaction.Direction.INCOMING,
                status=Transaction.Status.COMPLETED
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'this_month_revenue': Transaction.objects.filter(
                direction=Transaction.Direction.INCOMING,
                status=Transaction.Status.COMPLETED,
                completed_at__gte=start_of_month
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'last_month_revenue': Transaction.objects.filter(
                direction=Transaction.Direction.INCOMING,
                status=Transaction.Status.COMPLETED,
                completed_at__gte=last_month_start,
                completed_at__lt=start_of_month
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'total_orders': Transaction.objects.filter(
                status=Transaction.Status.COMPLETED,
                direction=Transaction.Direction.INCOMING
            ).count(),
            'pending_orders': Transaction.objects.filter(status=Transaction.Status.PENDING).count(),
            'failed_orders': Transaction.objects.filter(status=Transaction.Status.FAILED).count(),
            'refund_rate': 0,
            'active_subscriptions': Subscription.objects.filter(
                status__in=[Subscription.Status.ACTIVE, Subscription.Status.TRIALING]
            ).count(),
            'mrr': 0,
        }

        total_completed = Transaction.objects.filter(
            status=Transaction.Status.COMPLETED,
            direction=Transaction.Direction.INCOMING
        ).count()
        total_refunded = Refund.objects.filter(status=Refund.Status.COMPLETED).count()
        if total_completed > 0:
            stats['refund_rate'] = round((total_refunded / total_completed) * 100, 2)

        active_subs = Subscription.objects.filter(
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.TRIALING]
        )
        stats['mrr'] = sum(
            float(s.price) * (12 if s.interval == 'yearly' else 1)
            for s in active_subs
        ) / 12 if active_subs else 0

        return Response(stats)
