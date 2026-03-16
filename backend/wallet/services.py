from django.conf import settings


def build_wallet_deposit_reference(user) -> str:
    prefix = (getattr(settings, "BOG_DEPOSIT_REFERENCE_PREFIX", "EXP") or "EXP").strip().upper()
    return f"{prefix}-{int(user.id):06d}"
