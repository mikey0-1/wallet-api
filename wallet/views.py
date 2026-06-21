from django.db import transaction
from django.db.models import Q
from django.shortcuts import render
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from filters.filters import TransferFilter
from wallet.models import Wallet, Transfer, LedgerEntry
from wallet.serializers import WalletSerializer, LedgerEntrySerializer
from .serializers import TransferSerializer
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

class WalletView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletSerializer

    def get_object(self):
        return Wallet.objects.get(user=self.request.user)

class TransferView(APIView):

    @extend_schema(
        parameters=[
            OpenApiParameter(
            name="idempotency_key",
            type=OpenApiTypes.STR,
            location='header',
            required=True,
            description='Unique key to safely retry transfers without double-processing. '
                        'Use a UUID. If a transfer with this key already exists, the original result is returned instead of creating a new transfer.'
        )],
        request=TransferSerializer,
        responses={
            201: TransferSerializer,
            400: OpenApiTypes.OBJECT
        }
    )

    def post(self, request):

        # 1 - check if idempotency key from header
        idempotency_key = request.data.get('idempotency_key')
        if not idempotency_key:
            return Response({'error': 'idempotency_key is required'}, status=status.HTTP_400_BAD_REQUEST)

        # 2 - check if idempotency key is already used
        existing_transfer = Transfer.objects.filter(idempotency_key=idempotency_key).first()
        if existing_transfer:
            return Response(TransferSerializer(existing_transfer).data, status=status.HTTP_200_OK)

        # 3 - validate request
        serializer = TransferSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        recipient = serializer.validated_data['recipient']
        amount = serializer.validated_data['amount']
        description = serializer.validated_data.get('description', '')

        # 4 - run transfer inside atomic block
        with transaction.atomic():
            wallets = Wallet.objects.select_for_update().filter(user__in=[request.user, recipient]).order_by('id')

            sender_wallet = wallets.get(user=request.user)
            recipient_wallet = wallets.get(user=recipient)

            # record failed attempt
            if sender_wallet.balance < amount:
                Transfer.objects.create(
                    sender=request.user,
                    recipient=recipient,
                    amount=amount,
                    status=Transfer.TransferStatus.FAILED,
                    idempotency_key=idempotency_key,
                    description=description,
                )
                return Response({'error': 'transfer failed'}, status=status.HTTP_400_BAD_REQUEST)

            # transfer the money
            sender_wallet.balance -= amount
            recipient_wallet.balance += amount
            sender_wallet.save()
            recipient_wallet.save()

            # record the transfer
            transfer = Transfer.objects.create(
                sender=request.user,
                recipient=recipient,
                amount=amount,
                status=Transfer.TransferStatus.COMPLETED,
                idempotency_key=idempotency_key,
                description=description,
            )

            # create ledger entries
            LedgerEntry.objects.create(
                wallet = sender_wallet,
                transfer = transfer,
                entry_type=LedgerEntry.LedgerEntryChoices.DEBIT,
                amount=amount,
                balance_after=sender_wallet.balance,
            )

            LedgerEntry.objects.create(
                wallet = recipient_wallet,
                transfer = transfer,
                entry_type=LedgerEntry.LedgerEntryChoices.CREDIT,
                amount=amount,
                balance_after=recipient_wallet.balance,
            )

        return Response(TransferSerializer(transfer).data, status=status.HTTP_200_OK)

class TransferListView(generics.ListAPIView):
    serializer_class = TransferSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = TransferFilter

    def get_queryset(self):
        return Transfer.objects.filter (Q(user=self.request.user) | Q(recipient=self.request.user)).order_by('-created_at')

class TransferDetailView(generics.RetrieveAPIView):
    serializer_class = TransferSerializer

    def get_object(self):
        transfer = Transfer.objects.filter (Q(user=self.request.user) | Q(recipient=self.request.user),
                                            pk=self.kwargs['pk']).first()
        if not transfer:
            raise NotFound()
        return transfer

class LedgerEntryListView(generics.ListAPIView):
    serializer_class = LedgerEntrySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = TransferFilter

    def get_queryset(self):
        return LedgerEntry.objects.filter(wallet__user=self.request.user).order_by('-created_at')
