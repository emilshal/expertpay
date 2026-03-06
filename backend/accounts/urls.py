from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    FleetListView,
    FleetMemberRoleUpdateView,
    FleetMembersView,
    MeView,
    RegisterView,
    RequestFleetCodeView,
    VerifyFleetCodeView,
)


urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("fleets/", FleetListView.as_view(), name="fleet-list"),
    path("request-code/", RequestFleetCodeView.as_view(), name="request-fleet-code"),
    path("verify-code/", VerifyFleetCodeView.as_view(), name="verify-fleet-code"),
    path("fleet-members/", FleetMembersView.as_view(), name="fleet-members"),
    path("fleet-members/role/", FleetMemberRoleUpdateView.as_view(), name="fleet-member-role-update"),
]
