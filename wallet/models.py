from django.db import models
from accounts.models import CustomUser
from django.conf import settings

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)

    def __str__(self):
        return "f(self.user.username) Wallet"
