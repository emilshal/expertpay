from django.urls import path

from .views import (
    AdminNetworkSummaryView,
    BalanceView,
    BankAccountListCreateView,
    DepositInstructionsView,
    DepositListView,
    OwnerDriverFinanceListView,
    OwnerFleetSummaryView,
    OwnerTransactionListView,
    DepositSyncView,
    IncomingTransferManualMatchView,
    TransactionListView,
    UnmatchedIncomingTransferListView,
    WalletTopUpView,
    WithdrawalCreateView,
    WithdrawalListView,
    WithdrawalStatusUpdateView,
)


urlpatterns = [
    path("balance/", BalanceView.as_view(), name="wallet-balance"),
    path("bank-accounts/", BankAccountListCreateView.as_view(), name="bank-account-list-create"),
    path("admin-network-summary/", AdminNetworkSummaryView.as_view(), name="admin-network-summary"),
    path("owner-summary/", OwnerFleetSummaryView.as_view(), name="owner-fleet-summary"),
    path("owner-driver-finance/", OwnerDriverFinanceListView.as_view(), name="owner-driver-finance"),
    path("owner-transactions/", OwnerTransactionListView.as_view(), name="owner-transactions"),
    path("deposit-instructions/", DepositInstructionsView.as_view(), name="deposit-instructions"),
    path("deposits/", DepositListView.as_view(), name="deposit-list"),
    path("deposits/sync/", DepositSyncView.as_view(), name="deposit-sync"),
    path("incoming-transfers/unmatched/", UnmatchedIncomingTransferListView.as_view(), name="incoming-transfer-unmatched"),
    path(
        "incoming-transfers/<int:transfer_id>/match/",
        IncomingTransferManualMatchView.as_view(),
        name="incoming-transfer-manual-match",
    ),
    path("transactions/", TransactionListView.as_view(), name="transaction-list"),
    path("top-up/", WalletTopUpView.as_view(), name="wallet-top-up"),
    path("withdrawals/", WithdrawalCreateView.as_view(), name="withdrawal-create"),
    path("withdrawals/list/", WithdrawalListView.as_view(), name="withdrawal-list"),
    path(
        "withdrawals/<int:withdrawal_id>/status/",
        WithdrawalStatusUpdateView.as_view(),
        name="withdrawal-status-update",
    ),
]
