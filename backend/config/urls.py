from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/integrations/", include("integrations.urls")),
    path("api/", include("payments.urls")),
    path("api/wallet/", include("wallet.urls")),
]
