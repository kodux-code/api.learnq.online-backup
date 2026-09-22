import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when the SMTP server does not accept an email for delivery."""


def send_templated_email(*, subject, recipient, template_name, context):
    """Render and submit one transactional email through the configured mailer."""
    html_content = render_to_string(template_name, context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_content),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(html_content, "text/html")

    try:
        sent_count = message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("Transactional email submission failed for %s", recipient)
        raise EmailDeliveryError("The email service is temporarily unavailable.") from exc

    if sent_count != 1:
        logger.error("Transactional email was not accepted for %s", recipient)
        raise EmailDeliveryError("The email service did not accept the message.")