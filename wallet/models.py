from django.db import models
from django.conf import settings
from django.core.exceptions import PermissionDenied


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)

    def __str__(self):
        return "f(self.user.username) Wallet"

class Transfer(models.Model):
    class TransferStatus(models.TextChoices):
        PENDING = 'P', 'Pending'
        COMPLETED = 'C', 'Completed'
        FAILED = 'F', 'Failed'

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_transfers')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_transfers')
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    status = models.CharField(max_length=1, choices=TransferStatus.choices)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Transfer {self.id} from {self.sender} to {self.recipient} ({self.amount})"

class LedgerEntry(models.Model):
    class LedgerEntryChoices(models.TextChoices):
        DEBIT = 'DR', 'Debit'
        CREDIT = 'CR', 'Credit'

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='ledger_entries')
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=2, choices=LedgerEntryChoices.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Function for entry of ledger
    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied('Ledger entries are append-only and cannot be updated.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied('Ledger entries are append-only and cannot be deleted.')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.entry_type} | {self.amount} | Wallet: {self.wallet_id}"