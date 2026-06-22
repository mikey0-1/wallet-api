# P2P Wallet & Transfers API

A peer-to-peer payment API built with Django REST Framework. Users can hold a wallet balance, send money to other users, and view a full transaction history through a double-entry ledger.

**Stack:** Python, Django, Django REST Framework, PostgreSQL, JWT authentication  
**Deployed on:** Railway

---

## Live API

Base URL: `wallet-api-production-1816.up.railway.app`  
Swagger docs: `wallet-api-production-1816.up.railway.app/api/docs/`

---

## Features

- Email-based JWT authentication (register, login, refresh)
- Each user has one wallet with a real-time balance
- P2P transfers with idempotency — safe to retry without double-charging
- Double-entry ledger — every transfer creates two immutable records
- Full transfer and ledger history with filtering and cursor pagination
- Data isolation — users can only ever see their own wallet and transactions

---

## Key Design Decisions

### Idempotency

Every transfer request requires an `Idempotency-Key` header (a UUID chosen by the client). Before processing anything, the API checks whether a transfer with that key already exists. If it does, the original result is returned immediately — no second transfer is created.

```
POST /api/wallet/transfers/create/
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

This is the same pattern used by Stripe. It solves a real problem: if a client sends a transfer request and the network drops before they receive the response, they don't know whether the transfer went through. With idempotency, they can safely retry with the same key — if it already processed, they get the original result; if it didn't, it processes now. Either way, money only moves once.

The idempotency key is stored directly on the `Transfer` row with a `unique` database constraint. This means even if two identical requests hit the server simultaneously, only one `INSERT` will succeed at the database level. The key lives in the header rather than the request body — this is intentional, keeping it separate from business data and making it clear it is infrastructure-level metadata.

Failed transfers (insufficient funds) are also recorded with their idempotency key. This ensures that retrying a failed transfer with the same key returns the same failure — not a second attempt.

### Double-Entry Ledger

Every successful transfer creates exactly two `LedgerEntry` rows:

- A **debit** entry on the sender's wallet
- A **credit** entry on the recipient's wallet

Each entry stores a `balance_after` snapshot — the wallet balance at the moment that entry was written. This means the ledger is a complete, point-in-time audit trail. You can reconstruct the full balance history of any wallet by reading its ledger entries in order.

This is the same principle used in real accounting and fintech systems. The `Wallet.balance` field is a cached running total for fast reads, but the ledger is the source of truth. A reconciliation check can verify this at any time:

```python
# The most recent balance_after on the ledger must always match the wallet's cached balance
latest_entry = LedgerEntry.objects.filter(wallet=wallet).order_by('-created_at').first()
assert latest_entry.balance_after == wallet.balance
```

`LedgerEntry` is append-only by design — the model's `save()` method raises an error if you attempt to update an existing entry, and `delete()` is blocked entirely. This is enforced at the model level, not just the API level, so no code path anywhere in the application can silently corrupt the audit trail.

### Atomic Transfers with Row-Level Locking

The transfer logic runs inside a single `transaction.atomic()` block. Both wallets are locked at the start using `select_for_update()`, always in a consistent order (by wallet ID) regardless of which user is sender and which is recipient.

The consistent ordering prevents deadlocks. Without it, two simultaneous transfers between the same two users in opposite directions could each lock one wallet and then wait forever for the other — a classic deadlock. Locking in a deterministic order means both transactions always acquire locks in the same sequence, so one will always proceed while the other waits.

Within the atomic block, the following all happen together or not at all:
1. Sender balance decremented
2. Recipient balance incremented
3. Transfer record created
4. Two LedgerEntry rows created

If anything fails mid-way, the entire transaction rolls back. The wallet balances and ledger will never be left in an inconsistent state.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/register/` | Register a new user |
| POST | `/api/login/` | Obtain JWT token pair |
| POST | `/api/refresh/` | Refresh access token |
| GET/PATCH | `/api/profile/` | View or update your profile |
| GET | `/api/wallet/` | View your wallet balance |
| POST | `/api/transfers/create/` | Send money to another user |
| GET | `/api/transfers/` | List your transfers |
| GET | `/api/transfers/{id}/` | Retrieve one transfer |
| GET | `/api/ledger/` | View your ledger (transaction statement) |

---

## Making a Transfer

```bash
curl -X POST https://yourapp.up.railway.app/api/wallet/transfers/create/ \
  -H "Authorization: Bearer <your_token>" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"recipient": 2, "amount": "50.00", "description": "lunch"}'
```

To safely retry, send the exact same request with the same `Idempotency-Key`. The response will be identical and no second transfer will occur.

---

## Running Locally

```bash
git clone https://github.com/yourusername/WalletAPI
cd WalletAPI
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`) and set up your PostgreSQL database, then:

```bash
python manage.py migrate
python manage.py runserver
```

---

## Running Tests

```bash
python manage.py test wallet.tests
```

Tests cover: happy path transfers, idempotency, insufficient funds, self-transfer rejection, data isolation (404 pattern), and ledger reconciliation.
