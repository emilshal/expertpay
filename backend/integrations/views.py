from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProviderConnection
from .serializers import ExternalEventSerializer, ProviderConnectionSerializer, SimulateEventsSerializer
from .services import generate_simulated_events, import_unprocessed_events, reconciliation_summary


def _get_or_create_yandex_connection(user):
    connection, _ = ProviderConnection.objects.get_or_create(
        user=user,
        provider=ProviderConnection.Provider.YANDEX,
        external_account_id=f"fleet-{user.username}",
        defaults={"status": "active", "config": {"mode": "simulator"}},
    )
    return connection


class ConnectYandexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        return Response(ProviderConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


class ListYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        events = connection.events.order_by("-created_at")[:100]
        return Response(ExternalEventSerializer(events, many=True).data)


class SimulateYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SimulateEventsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode = serializer.validated_data["mode"]
        count = serializer.validated_data["count"]

        connection = _get_or_create_yandex_connection(request.user)
        created = generate_simulated_events(connection=connection, mode=mode, count=count)
        return Response(
            {
                "connection_id": connection.id,
                "mode": mode,
                "requested_count": count,
                "stored_count": len(created),
            },
            status=status.HTTP_201_CREATED,
        )


class ImportYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        result = import_unprocessed_events(connection=connection)
        return Response(result, status=status.HTTP_200_OK)


class ReconcileYandexView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        return Response(reconciliation_summary(connection=connection))
