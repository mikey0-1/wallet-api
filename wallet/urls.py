from .views import WalletView
from django.urls import path, include

urlpatterns = [
    path('', WalletView.as_view(), name='wallet'),
]