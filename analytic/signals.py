import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Count, Sum, Avg, F, Q
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .models import Event, DailyMetric, HourlyMetric, RetentionCohort

User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)


# Predefined metric configurations
METRIC_CONFIGS = {
    # User metrics
    'users.registered': {'metric_name': 'users.registered', 'metric_type': 'counter', 'event_type': 'user.registered'},
    'users.active': {'metric_name': 'users.active', 'metric_type': 'gauge', 'event_type': 'user.login'},
    'users.verified': {'metric_name': 'users.verified', 'metric_type': 'counter', 'event_type': 'user.verified'},
    'users.deactivated': {'metric_name': 'users.deactivated', 'metric_type': 'counter', 'event_type': 'user.deactivated'},
    
    # Course metrics
    'courses.created': {'metric_name': 'courses.created', 'metric_type': 'counter', 'event_type': 'course.created'},
    'courses.published': {'metric_name': 'courses.published', 'metric_type': 'counter', 'event_type': 'course.published'},
    'courses.enrolled': {'metric_name': 'courses.enrolled', 'metric_type': 'counter', 'event_type': 'course.enrolled'},
    'courses.completed': {'metric_name': 'courses.completed', 'metric_type': 'counter', 'event_type': 'course.completed'},
    'courses.dropped': {'metric_name': 'courses.dropped', 'metric_type': 'counter', 'event_type': 'course.dropped'},
    'lectures.completed': {'metric_name': 'lectures.completed', 'metric_type': 'counter', 'event_type': 'lecture.completed'},
    
    # Assessment metrics
    'assessments.started': {'metric_name': 'assessments.started', 'metric_type': 'counter', 'event_type': 'assessment.started'},
    'assessments.submitted': {'metric_name': 'assessments.submitted', 'metric_type': 'counter', 'event_type': 'assessment.submitted'},
    'assessments.passed': {'metric_name': 'assessments.passed', 'metric_type': 'counter', 'event_type': 'assessment.passed'},
    'assessments.failed': {'metric_name': 'assessments.failed', 'metric_type': 'counter', 'event_type': 'assessment.failed'},
    
    # Payment metrics
    'payments.initiated': {'metric_name': 'payments.initiated', 'metric_type': 'counter', 'event_type': 'payment.initiated'},
    'payments.completed': {'metric_name': 'payments.completed', 'metric_type': 'counter', 'event_type': 'payment.completed'},
    'payments.failed': {'metric_name': 'payments.failed', 'metric_type': 'counter', 'event_type': 'payment.failed'},
    'payments.refunded': {'metric_name': 'payments.refunded', 'metric_type': 'counter', 'event_type': 'payment.refunded'},
    'revenue.gross': {'metric_name': 'revenue.gross', 'metric_type': 'counter', 'event_type': 'payment.completed', 'sum_field': 'properties.amount'},
    'revenue.net': {'metric_name': 'revenue.net', 'metric_type': 'counter', 'event_type': 'payment.completed', 'sum_field': 'properties.net_amount'},
    'subscriptions.started': {'metric_name': 'subscriptions.started', 'metric_type': 'counter', 'event_type': 'subscription.started'},
    'subscriptions.cancelled': {'metric_name': 'subscriptions.cancelled', 'metric_type': 'counter', 'event_type': 'subscription.cancelled'},
    
    # Earning metrics
    'earnings.accrued': {'metric_name': 'earnings.accrued', 'metric_type': 'counter', 'event_type': 'earning.accrued', 'sum_field': 'properties.amount'},
    'payouts.requested': {'metric_name': 'payouts.requested', 'metric_type': 'counter', 'event_type': 'payout.requested'},
    'payouts.completed': {'metric_name': 'payouts.completed', 'metric_type': 'counter', 'event_type': 'payout.completed'},
    
    # Engagement metrics
    'messages.sent': {'metric_name': 'messages.sent', 'metric_type': 'counter', 'event_type': 'message.sent'},
    'threads.created': {'metric_name': 'threads.created', 'metric_type': 'counter', 'event_type': 'thread.created'},
    'posts.created': {'metric_name': 'posts.created', 'metric_type': 'counter', 'event_type': 'post.created'},
    'comments.created': {'metric_name': 'comments.created', 'metric_type': 'counter', 'event_type': 'comment.created'},
    'likes.created': {'metric_name': 'likes.created', 'metric_type': 'counter', 'event_type': 'like.created'},
    'reviews.created': {'metric_name': 'reviews.created', 'metric_type': 'counter', 'event_type': 'review.created'},
    
    # Notification metrics
    'notifications.sent': {'metric_name': 'notifications.sent', 'metric_type': 'counter', 'event_type': 'notification.sent'},
    'notifications.opened': {'metric_name': 'notifications.opened', 'metric_type': 'counter', 'event_type': 'notification.opened'},
    'notifications.clicked': {'metric_name': 'notifications.clicked', 'metric_type': 'counter', 'event_type': 'notification.clicked'},
    
    # System metrics
    'errors.count': {'metric_name': 'errors.count', 'metric_type': 'counter', 'event_type': 'error.occurred'},
    'api.requests': {'metric_name': 'api.requests', 'metric_type': 'counter', 'event_type': 'api.request'},
    'api.duration': {'metric_name': 'api.duration', 'metric_type': 'histogram', 'event_type': 'api.request', 'sum_field': 'properties.duration_ms'},
    'page.views': {'metric_name': 'page.views', 'metric_type': 'counter', 'event_type': 'page.view'},
}


@receiver(post_save, sender=Event)
def aggregate_event_metrics(sender, instance, created, **kwargs):
    """Aggregate event into hourly and daily metrics."""
    if not created:
        return
    
    event_type = instance.event_type
    config = METRIC_CONFIGS.get(event_type)
    if not config:
        return
    
    timestamp = instance.timestamp
    date = timestamp.date()
    hour = timestamp.replace(minute=0, second=0, microsecond=0)
    
    # Dimensions
    dimensions = {}
    if instance.user:
        dimensions['user_role'] = instance.user.role
    dimensions['source_app'] = instance.source_app or 'unknown'
    
    # Extract custom dimensions from properties
    for key in ['country', 'device_type', 'course_id', 'assessment_id', 'plan_id']:
        if key in instance.properties:
            dimensions[key] = str(instance.properties[key])
    
    # Calculate values
    count = 1
    sum_value = 0
    if config.get('sum_field'):
        sum_value = instance.properties.get(config['sum_field'].split('.')[-1], 0)
        if isinstance(sum_value, (int, float)):
            sum_value = float(sum_value)
        else:
            sum_value = 0
    
    metric_name = config['metric_name']
    metric_type = config['metric_type']
    
    # Update daily metric
    for dim_key, dim_value in dimensions.items():
        DailyMetric.objects.update_or_create(
            date=date,
            metric_name=metric_name,
            metric_type=metric_type,
            app=dimensions.get('source_app', ''),
            user_role=dimensions.get('user_role', ''),
            country=dimensions.get('country', ''),
            device_type=dimensions.get('device_type', ''),
            dimension_key=dim_key,
            dimension_value=dim_value,
            defaults={
                'count': F('count') + count,
                'sum_value': F('sum_value') + sum_value,
            }
        )
    
    # Update without dimension breakdown
    DailyMetric.objects.update_or_create(
        date=date,
        metric_name=metric_name,
        metric_type=metric_type,
        app=dimensions.get('source_app', ''),
        user_role=dimensions.get('user_role', ''),
        country=dimensions.get('country', ''),
        device_type=dimensions.get('device_type', ''),
        dimension_key='',
        dimension_value='',
        defaults={
            'count': F('count') + count,
            'sum_value': F('sum_value') + sum_value,
        }
    )
    
    # Update hourly metric
    HourlyMetric.objects.update_or_create(
        hour=hour,
        metric_name=metric_name,
        app=dimensions.get('source_app', ''),
        defaults={
            'count': F('count') + count,
            'sum_value': F('sum_value') + sum_value,
        }
    )


def compute_retention_cohorts():
    """Management command to compute retention cohorts. Run daily via cron."""
    from django.contrib.auth import get_user_model
    from course.models import Enrollment
    from assessment.models import Attempt
    
    today = timezone.now().date()
    
    # Compute for last 30 days
    for days_ago in range(1, 31):
        cohort_date = today - timedelta(days=days_ago)
        
        # Get users who first enrolled/logged in on cohort_date
        cohort_users = User.objects.filter(
            date_joined__date=cohort_date,
            is_active=True
        )
        
        # Or first course enrollment
        enrolled_users = Enrollment.objects.filter(
            enrolled_at__date=cohort_date
        ).values_list('student_id', flat=True)
        
        all_cohort_users = set(cohort_users.values_list('id', flat=True)) | set(enrolled_users)
        cohort_size = len(all_cohort_users)
        
        if cohort_size == 0:
            continue
        
        # Calculate retention for each period
        for period_type, max_periods in [('day', 30), ('week', 12), ('month', 6)]:
            for period in range(max_periods + 1):
                if period_type == 'day':
                    check_date = cohort_date + timedelta(days=period)
                elif period_type == 'week':
                    check_date = cohort_date + timedelta(weeks=period)
                else:
                    check_date = cohort_date + timedelta(days=period * 30)
                
                if check_date > today:
                    break
                
                # Check who was active on check_date
                active_on_date = Event.objects.filter(
                    user_id__in=all_cohort_users,
                    timestamp__date=check_date
                ).values_list('user_id', flat=True).distinct()
                
                retained = len(active_on_date)
                rate = (retained / cohort_size * 100) if cohort_size > 0 else 0
                
                RetentionCohort.objects.update_or_create(
                    cohort_date=cohort_date,
                    period=period,
                    period_type=period_type,
                    defaults={
                        'cohort_size': cohort_size,
                        'retained_users': retained,
                        'retention_rate': round(rate, 2),
                    }
                )
