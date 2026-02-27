from django.urls import path

from .views import InternalTransferByBankView, InternalTransferCreateView


urlpatterns = [
    path("transfers/internal/", InternalTransferCreateView.as_view(), name="internal-transfer-create"),
    path("transfers/internal/by-bank/", InternalTransferByBankView.as_view(), name="internal-transfer-by-bank"),
]
