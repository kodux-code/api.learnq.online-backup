import random
from django.core.cache import cache
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

EMAIL_VERIFY_SIGNER = TimestampSigner(salt='vTH5Ep6odU2SNg_aPXmxpw')
TOKEN_EXPIRY_SECONDS = 86400
PASSWORD_RESET_SIGNER = TimestampSigner(salt='client-password-reset-salt')
PASSWORD_RESET_EXPIRY_SECONDS = 900
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 600  # 10 minutes


def generate_verification_token(client_id: str) -> str:
    return EMAIL_VERIFY_SIGNER.sign(str(client_id))


def verify_and_extract_client_id(token: str) -> str | None:
    try:
        client_id = EMAIL_VERIFY_SIGNER.unsign(token, max_age=TOKEN_EXPIRY_SECONDS)
        return client_id
    except (BadSignature, SignatureExpired):
        return None


def generate_password_reset_token(client_id: str) -> str:
    return PASSWORD_RESET_SIGNER.sign(str(client_id))


def verify_and_extract_reset_id(token: str) -> str | None:
    try:
        return PASSWORD_RESET_SIGNER.unsign(token, max_age=PASSWORD_RESET_EXPIRY_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def generate_otp() -> str:
    """Generate a 6-digit OTP code."""
    return ''.join(str(random.randint(0, 9)) for _ in range(OTP_LENGTH))


def store_otp(client_id: str, otp: str) -> None:
    """Store OTP in cache with expiry."""
    cache.set(f'otp:{client_id}', otp, OTP_EXPIRY_SECONDS)


def verify_otp(client_id: str, otp: str) -> bool:
    """Verify OTP against stored value."""
    stored_otp = cache.get(f'otp:{client_id}')
    if stored_otp and stored_otp == otp:
        cache.delete(f'otp:{client_id}')
        return True
    return False


def resend_otp_allowed(client_id: str) -> bool:
    """Check if OTP can be resent (cooldown)."""
    return not cache.get(f'otp_resend_cooldown:{client_id}')


def set_resend_cooldown(client_id: str, seconds: int = 60) -> None:
    """Set resend cooldown."""
    cache.set(f'otp_resend_cooldown:{client_id}', True, seconds)