from django.urls import path

from .views import (
    ConnectBankSimulatorView,
    ConnectYandexView,
    ImportYandexEventsView,
    ListBankSimulatorPayoutsView,
    ListYandexCategoriesView,
    ListYandexEventsView,
    ListYandexSyncRunsView,
    ReconcileYandexView,
    ReconciliationSummaryView,
    SimulateYandexEventsView,
    SyncYandexCategoriesView,
    SyncLiveYandexView,
    SubmitBankSimulatorPayoutView,
    TestYandexConnectionView,
    UpdateBankSimulatorPayoutStatusView,
)


urlpatterns = [
    path("yandex/connect/", ConnectYandexView.as_view(), name="yandex-connect"),
    path("yandex/test-connection/", TestYandexConnectionView.as_view(), name="yandex-test-connection"),
    path("yandex/sync-live/", SyncLiveYandexView.as_view(), name="yandex-sync-live"),
    path("yandex/sync-categories/", SyncYandexCategoriesView.as_view(), name="yandex-sync-categories"),
    path("yandex/categories/", ListYandexCategoriesView.as_view(), name="yandex-categories"),
    path("yandex/sync-runs/", ListYandexSyncRunsView.as_view(), name="yandex-sync-runs"),
    path("yandex/events/", ListYandexEventsView.as_view(), name="yandex-events"),
    path("yandex/simulate-events/", SimulateYandexEventsView.as_view(), name="yandex-simulate"),
    path("yandex/import/", ImportYandexEventsView.as_view(), name="yandex-import"),
    path("yandex/reconcile/", ReconcileYandexView.as_view(), name="yandex-reconcile"),
    path("bank-sim/connect/", ConnectBankSimulatorView.as_view(), name="bank-sim-connect"),
    path("bank-sim/payouts/", ListBankSimulatorPayoutsView.as_view(), name="bank-sim-payouts"),
    path("bank-sim/payouts/submit/", SubmitBankSimulatorPayoutView.as_view(), name="bank-sim-submit"),
    path(
        "bank-sim/payouts/<int:payout_id>/status/",
        UpdateBankSimulatorPayoutStatusView.as_view(),
        name="bank-sim-status-update",
    ),
    path("reconciliation/summary/", ReconciliationSummaryView.as_view(), name="reconciliation-summary"),
]
