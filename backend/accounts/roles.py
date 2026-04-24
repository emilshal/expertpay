from .models import FleetPhoneBinding


ROLE_RANK = {
    FleetPhoneBinding.Role.DRIVER: 1,
    FleetPhoneBinding.Role.OPERATOR: 2,
    FleetPhoneBinding.Role.ADMIN: 3,
    FleetPhoneBinding.Role.OWNER: 4,
}


def get_request_fleet_binding(*, user, request):
    if user is None or not user.is_authenticated:
        return None

    bindings = FleetPhoneBinding.objects.filter(
        user=user,
        is_active=True,
        user__is_active=True,
    ).select_related("fleet")

    fleet_name = (request.headers.get("X-Fleet-Name") or request.query_params.get("fleet_name") or "").strip()
    if fleet_name:
        bindings = bindings.filter(fleet__name__iexact=fleet_name)

    active_role = (request.headers.get("X-Active-Role") or request.query_params.get("role") or "").strip().lower()
    if active_role in ROLE_RANK:
        role_bindings = bindings.filter(role=active_role)
        if role_bindings.exists():
            bindings = role_bindings

    if not bindings.exists():
        return None

    candidates = list(bindings)
    if not candidates:
        return None

    candidates.sort(
        key=lambda binding: (
            ROLE_RANK.get(binding.role, 0),
            binding.created_at or 0,
            binding.id,
        ),
        reverse=True,
    )
    return candidates[0]


def meets_min_role(*, binding, minimum_role):
    if binding is None:
        return False
    return ROLE_RANK.get(binding.role, 0) >= ROLE_RANK.get(minimum_role, 999)


def is_platform_admin(*, user):
    return bool(user and user.is_authenticated and user.is_staff)
