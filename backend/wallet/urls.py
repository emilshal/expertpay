from django.urls import path

from .views import (
    BalanceView,
    BankAccountListCreateView,
    TransactionListView,
    WithdrawalCreateView,
    WithdrawalListView,
    WithdrawalStatusUpdateView,
)


urlpatterns = [
    path("balance/", BalanceView.as_view(), name="wallet-balance"),
    path("bank-accounts/", BankAccountListCreateView.as_view(), name="bank-account-list-create"),
    path("transactions/", TransactionListView.as_view(), name="transaction-list"),
    path("withdrawals/", WithdrawalCreateView.as_view(), name="withdrawal-create"),
    path("withdrawals/list/", WithdrawalListView.as_view(), name="withdrawal-list"),
    path(
        "withdrawals/<int:withdrawal_id>/status/",
        WithdrawalStatusUpdateView.as_view(),
        name="withdrawal-status-update",
    ),
]
