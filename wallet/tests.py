from decimal import Decimal
import uuid
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from wallet.models import Transfer, LedgerEntry

User = get_user_model()


class WalletTransferTests(APITestCase):

    def setUp(self):
        # 1. Create Users
        self.sender = User.objects.create_user(
            email='sender@example.com',
            password='Password123!',
            first_name='Alice',
            last_name='Sender'
        )
        self.recipient = User.objects.create_user(
            email='recipient@example.com',
            password='Password123!',
            first_name='Bob',
            last_name='Recipient'
        )
        self.intruder = User.objects.create_user(
            email='intruder@example.com',
            password='Password123!',
            first_name='Eve',
            last_name='Intruder'
        )

        # 2. Fund the Sender's Wallet (Signal already created it with 0.00)
        self.sender.wallet.balance = Decimal('1000.00')
        self.sender.wallet.save()

        # 3. Dynamic URLs using names from urls.py
        self.transfer_url = reverse('transfer-create')
        self.ledger_url = reverse('ledger-list')
        # Note: 'transfer-detail' is omitted here because it requires a pk argument!

    def test_happy_path_successful_transfer(self):
        """
        Happy path: successful transfer reduces sender balance, increases recipient balance,
        and creates exactly two LedgerEntry rows.
        """
        self.client.force_authenticate(user=self.sender)
        transfer_amount = Decimal('150.00')
        idemp_key = str(uuid.uuid4())

        payload = {
            'recipient': self.recipient.id,
            'amount': transfer_amount,
            'description': 'Dinner split'
        }

        # Header passed as HTTP_IDEMPOTENCY_KEY to match request.headers.get('Idempotency-Key')
        response = self.client.post(self.transfer_url, payload, HTTP_IDEMPOTENCY_KEY=idemp_key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh balances from DB
        self.sender.wallet.refresh_from_db()
        self.recipient.wallet.refresh_from_db()

        # Assert balances changed correctly
        self.assertEqual(self.sender.wallet.balance, Decimal('850.00'))
        self.assertEqual(self.recipient.wallet.balance, Decimal('150.00'))

        # Assert exactly one transfer created with COMPLETED status
        self.assertEqual(Transfer.objects.count(), 1)
        transfer = Transfer.objects.first()
        self.assertEqual(transfer.status, Transfer.TransferStatus.COMPLETED)

        # Assert exactly two ledger entries exist
        self.assertEqual(LedgerEntry.objects.count(), 2)
        debit_entry = LedgerEntry.objects.get(entry_type=LedgerEntry.LedgerEntryChoices.DEBIT)
        credit_entry = LedgerEntry.objects.get(entry_type=LedgerEntry.LedgerEntryChoices.CREDIT)

        self.assertEqual(debit_entry.wallet, self.sender.wallet)
        self.assertEqual(debit_entry.amount, transfer_amount)
        self.assertEqual(credit_entry.wallet, self.recipient.wallet)
        self.assertEqual(credit_entry.amount, transfer_amount)

    def test_idempotency_identical_requests(self):
        """
        Idempotency test: identical transfer request sent twice with same Idempotency-Key.
        Assert only ONE Transfer and ONE pair of LedgerEntry rows exist.
        """
        self.client.force_authenticate(user=self.sender)
        idemp_key = str(uuid.uuid4())
        payload = {
            'recipient': self.recipient.id,
            'amount': '100.00'
        }

        # First request
        response_one = self.client.post(self.transfer_url, payload, HTTP_IDEMPOTENCY_KEY=idemp_key)
        self.assertEqual(response_one.status_code, status.HTTP_200_OK)

        # Second identical request
        response_two = self.client.post(self.transfer_url, payload, HTTP_IDEMPOTENCY_KEY=idemp_key)
        self.assertEqual(response_two.status_code, status.HTTP_200_OK)

        # Assert DB only has one transaction set despite two 200 OK responses
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 2)

        # Assert balance only dropped once
        self.sender.wallet.refresh_from_db()
        self.assertEqual(self.sender.wallet.balance, Decimal('900.00'))

    def test_insufficient_funds_rejection(self):
        """
        Insufficient funds test: transfer rejected, sender balance unchanged,
        a failed Transfer record exists.
        """
        self.client.force_authenticate(user=self.sender)
        idemp_key = str(uuid.uuid4())
        payload = {
            'recipient': self.recipient.id,
            'amount': '5000.00',  # More than the 1000.00 balance
        }

        response = self.client.post(self.transfer_url, payload, HTTP_IDEMPOTENCY_KEY=idemp_key)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'transfer failed')

        # Assert balance unchanged
        self.sender.wallet.refresh_from_db()
        self.assertEqual(self.sender.wallet.balance, Decimal('1000.00'))

        # Assert Failed Transfer record exists, but NO ledger entries
        transfer = Transfer.objects.first()
        self.assertEqual(transfer.status, Transfer.TransferStatus.FAILED)
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_self_transfer_rejection(self):
        """
        Self-transfer rejection test: User cannot send funds to themselves.
        """
        self.client.force_authenticate(user=self.sender)
        idemp_key = str(uuid.uuid4())
        payload = {
            'recipient': self.sender.id,  # Sending to self
            'amount': '100.00',
        }

        response = self.client.post(self.transfer_url, payload, HTTP_IDEMPOTENCY_KEY=idemp_key)

        # Assert serializer caught the error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.assertEqual(
            response.data['non_field_errors'][0],
            'You cannot transfer money to your own wallet'
        )
        self.assertEqual(Transfer.objects.count(), 0)

    def test_data_isolation(self):
        """
        Data isolation tests: User A cannot view User B's transfers or ledger.
        """
        # 1. Sender makes a transfer to Recipient
        self.client.force_authenticate(user=self.sender)
        idemp_key = str(uuid.uuid4())
        self.client.post(self.transfer_url, {
            'recipient': self.recipient.id,
            'amount': '50.00'
        }, HTTP_IDEMPOTENCY_KEY=idemp_key)

        transfer_id = Transfer.objects.first().id

        # 2. Intruder logs in
        self.client.force_authenticate(user=self.intruder)

        # 3. Intruder tries to access the specific transfer detail (404 expected)
        # We safely call reverse here because we finally have an absolute transfer_id!
        detail_url = reverse('transfer-detail', kwargs={'pk': transfer_id})
        response_detail = self.client.get(detail_url)
        self.assertEqual(response_detail.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Intruder tries to pull their ledger list (should be empty, cannot see A/B)
        response_ledger = self.client.get(self.ledger_url)
        self.assertEqual(response_ledger.status_code, status.HTTP_200_OK)

        # Adjust depending on if you are using pagination or a raw list response:
        if isinstance(response_ledger.data, dict) and 'results' in response_ledger.data:
            self.assertEqual(len(response_ledger.data['results']), 0)
        else:
            self.assertEqual(len(response_ledger.data), 0)

    def test_reconciliation(self):
        """
        Reconciliation test: sum of all LedgerEntry amounts for a wallet
        equals that wallet's cached balance.
        """
        self.client.force_authenticate(user=self.sender)

        # We will make 3 separate transfers of 50.00 each
        for _ in range(3):
            self.client.post(self.transfer_url, {
                'recipient': self.recipient.id,
                'amount': '50.00'
            }, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        self.sender.wallet.refresh_from_db()
        self.recipient.wallet.refresh_from_db()

        # Test Recipient Reconciliation (Started at 0.00)
        recipient_credits = LedgerEntry.objects.filter(
            wallet=self.recipient.wallet,
            entry_type=LedgerEntry.LedgerEntryChoices.CREDIT
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        recipient_debits = LedgerEntry.objects.filter(
            wallet=self.recipient.wallet,
            entry_type=LedgerEntry.LedgerEntryChoices.DEBIT
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        recipient_calculated_balance = recipient_credits - recipient_debits
        self.assertEqual(recipient_calculated_balance, self.recipient.wallet.balance)
        self.assertEqual(self.recipient.wallet.balance, Decimal('150.00'))

        # Test Sender Reconciliation (Started at 1000.00)
        sender_credits = LedgerEntry.objects.filter(
            wallet=self.sender.wallet,
            entry_type=LedgerEntry.LedgerEntryChoices.CREDIT
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        sender_debits = LedgerEntry.objects.filter(
            wallet=self.sender.wallet,
            entry_type=LedgerEntry.LedgerEntryChoices.DEBIT
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        sender_calculated_balance = Decimal('1000.00') + sender_credits - sender_debits
        self.assertEqual(sender_calculated_balance, self.sender.wallet.balance)
        self.assertEqual(self.sender.wallet.balance, Decimal('850.00'))