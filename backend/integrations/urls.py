from django.urls import path

from .views import (
    ConnectYandexView,
    ImportYandexEventsView,
    ListYandexEventsView,
    ReconcileYandexView,
    SimulateYandexEventsView,
)


urlpatterns = [
    path("yandex/connect/", ConnectYandexView.as_view(), name="yandex-connect"),
    path("yandex/events/", ListYandexEventsView.as_view(), name="yandex-events"),
    path("yandex/simulate-events/", SimulateYandexEventsView.as_view(), name="yandex-simulate"),
    path("yandex/import/", ImportYandexEventsView.as_view(), name="yandex-import"),
    path("yandex/reconcile/", ReconcileYandexView.as_view(), name="yandex-reconcile"),
]
