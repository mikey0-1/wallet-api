from .views import *
from django.urls import path, include

urlpatterns = [
    path('', WalletView.as_view(), name='wallet'),
    path('transfers/', TransferListView.as_view(), name='transfer-list'),
    path('transfer/create/', TransferView.as_view(), name='transfer-create'),
    path('transfers/<int:pk>/', TransferDetailView.as_view(), name='transfer-detail'),
    path('ledger/', LedgerEntryListView.as_view(), name='ledger-list'),
]