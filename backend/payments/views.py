from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import begin_idempotent_request, finalize_idempotent_request, log_audit
from ledger.models import LedgerAccount
from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_user_ledger_account,
)
from wallet.models import Wallet

from .models import InternalTransfer
from .serializers import InternalTransferByBankSerializer, InternalTransferCreateSerializer


def _execute_internal_transfer(*, sender, receiver, amount, note):
    sender_wallet, _ = Wallet.objects.get_or_create(user=sender)
    receiver_wallet, _ = Wallet.objects.get_or_create(user=receiver)
    sender_account = get_or_create_user_ledger_account(sender, sender_wallet.currency)
    receiver_account = get_or_create_user_ledger_account(receiver, receiver_wallet.currency)

    ensure_opening_entry(sender_account, sender_wallet.balance, created_by=sender)
    ensure_opening_entry(receiver_account, receiver_wallet.balance, created_by=sender)

    with db_transaction.atomic():
        # Lock in deterministic order to avoid deadlocks.
        account_ids = sorted([sender_account.id, receiver_account.id])
        locked_accounts = LedgerAccount.objects.select_for_update().filter(id__in=account_ids)
        locked_by_id = {account.id: account for account in locked_accounts}
        locked_sender = locked_by_id[sender_account.id]
        locked_receiver = locked_by_id[receiver_account.id]

        sender_balance = get_account_balance(locked_sender, sender_wallet.currency)
        receiver_balance = get_account_balance(locked_receiver, receiver_wallet.currency)

        if amount > sender_balance:
            raise ValueError("Insufficient wallet balance for this transfer.")

        transfer = InternalTransfer.objects.create(
            sender_wallet=sender_wallet,
            receiver_wallet=receiver_wallet,
            amount=amount,
            currency=sender_wallet.currency,
            status=InternalTransfer.Status.COMPLETED,
        )

        create_ledger_entry(
            account=locked_sender,
            amount=-amount,
            entry_type="internal_transfer_debit",
            created_by=sender,
            reference_type="internal_transfer",
            reference_id=str(transfer.id),
            metadata={
                "to_user_id": receiver.id,
                "description": f"Transfer to {receiver.username}",
                "note": note,
            },
        )
        create_ledger_entry(
            account=locked_receiver,
            amount=amount,
            entry_type="internal_transfer_credit",
            created_by=sender,
            reference_type="internal_transfer",
            reference_id=str(transfer.id),
            metadata={
                "from_user_id": sender.id,
                "description": f"Transfer from {sender.username}",
                "note": note,
            },
        )

        sender_wallet.balance = sender_balance - amount
        receiver_wallet.balance = receiver_balance + amount
        sender_wallet.save(update_fields=["balance", "updated_at"])
        receiver_wallet.save(update_fields=["balance", "updated_at"])

    return transfer, sender_wallet, receiver_wallet


class InternalTransferCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = request.headers.get("X-Request-ID", "")
        idempotency_key = request.headers.get("Idempotency-Key", "")
        endpoint = "/api/transfers/internal/"

        serializer = InternalTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receiver_username = serializer.validated_data["receiver_username"]
        amount = serializer.validated_data["amount"]
        note = serializer.validated_data.get("note", "")

        idempotency_record, replay_body, replay_status = begin_idempotent_request(
            user=request.user,
            method="POST",
            endpoint=endpoint,
            key=idempotency_key,
            payload=serializer.validated_data,
        )
        if replay_body is not None:
            return Response(replay_body, status=replay_status)

        sender = request.user
        receiver = User.objects.get(username=receiver_username)
        if sender.id == receiver.id:
            error_payload = {"detail": "You cannot transfer to your own account."}
            finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
            return Response(
                error_payload,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transfer, sender_wallet, _ = _execute_internal_transfer(
                sender=sender,
                receiver=receiver,
                amount=amount,
                note=note,
            )
        except ValueError as exc:
            error_payload = {"detail": str(exc)}
            finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
            return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

        response_payload = {
            "id": transfer.id,
            "status": transfer.status,
            "amount": transfer.amount,
            "currency": transfer.currency,
            "receiver_username": receiver.username,
        }
        finalize_idempotent_request(idempotency_record, status_code=201, response_body=response_payload)
        log_audit(
            user=sender,
            action="internal_transfer_created",
            resource_type="internal_transfer",
            resource_id=transfer.id,
            request_id=request_id,
            ip_address=request.META.get("REMOTE_ADDR"),
            metadata={"amount": str(amount), "currency": sender_wallet.currency, "receiver_id": receiver.id},
        )
        return Response(response_payload, status=status.HTTP_201_CREATED)


class InternalTransferByBankView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = request.headers.get("X-Request-ID", "")
        idempotency_key = request.headers.get("Idempotency-Key", "")
        endpoint = "/api/transfers/internal/by-bank/"

        serializer = InternalTransferByBankSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receiver = serializer.validated_data["receiver_user"]
        amount = serializer.validated_data["amount"]
        note = serializer.validated_data.get("note", "")

        idempotency_record, replay_body, replay_status = begin_idempotent_request(
            user=request.user,
            method="POST",
            endpoint=endpoint,
            key=idempotency_key,
            payload=serializer.validated_data,
        )
        if replay_body is not None:
            return Response(replay_body, status=replay_status)

        sender = request.user
        if sender.id == receiver.id:
            error_payload = {"detail": "You cannot transfer to your own account."}
            finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
            return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

        try:
            transfer, sender_wallet, _ = _execute_internal_transfer(
                sender=sender,
                receiver=receiver,
                amount=amount,
                note=note,
            )
        except ValueError as exc:
            error_payload = {"detail": str(exc)}
            finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
            return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

        response_payload = {
            "id": transfer.id,
            "status": transfer.status,
            "amount": transfer.amount,
            "currency": transfer.currency,
            "receiver_username": receiver.username,
        }
        finalize_idempotent_request(idempotency_record, status_code=201, response_body=response_payload)
        log_audit(
            user=sender,
            action="internal_transfer_created",
            resource_type="internal_transfer",
            resource_id=transfer.id,
            request_id=request_id,
            ip_address=request.META.get("REMOTE_ADDR"),
            metadata={
                "amount": str(amount),
                "currency": sender_wallet.currency,
                "receiver_id": receiver.id,
                "via": "bank_details",
            },
        )
        return Response(response_payload, status=status.HTTP_201_CREATED)
