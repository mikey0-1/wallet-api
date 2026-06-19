from django.shortcuts import render
from rest_framework import generics, permissions

from wallet.models import Wallet
from wallet.serializers import WalletSerializer

class WalletView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletSerializer

    def get_object(self):
        return Wallet.objects.get(user=self.request.user)
