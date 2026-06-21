from rest_framework import serializers
from wallet.models import Wallet, Transfer, LedgerEntry
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance']
        read_only_fields = ['balance']

class TransferSerializer(serializers.ModelSerializer):
    recipient = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=False)

    class Meta:
        model = Transfer
        fields = ['id', 'sender', 'recipient', 'amount', 'status', 'description', 'created_at']
        read_only_fields = ['id', 'sender', 'status', 'created_at']

    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError('Amount must be greater than 0')
        return value

    def validate(self, data):
        request = self.context.get('request')
        if request and data.get('recipient') == request.user:
            raise serializers.ValidationError('You cannot transfer money to your own wallet')
        return data

class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            'id',
            'wallet',
            'transfer',
            'entry_type',
            'amount',
            'balance_after',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'wallet',
            'transfer',
            'entry_type',
            'amount',
            'balance_after',
            'created_at',
        ]