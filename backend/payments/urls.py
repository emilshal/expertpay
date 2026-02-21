from django.urls import path

from .views import InternalTransferCreateView


urlpatterns = [
    path("transfers/internal/", InternalTransferCreateView.as_view(), name="internal-transfer-create"),
]
