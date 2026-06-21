import django_filters
from wallet.models import Transfer, LedgerEntry

class TransferFilter(django_filters.FilterSet):
    created_at_after = django_filters.DateTimeFilter(field_name='create_at', lookup_expr='gte')
    created_at_before = django_filters.DateTimeFilter(field_name='create_at', lookup_expr='lte')
    status = django_filters.ChoiceFilter(choices=Transfer.TransferStatus.choices)

    class Meta:
        model = Transfer
        fields = ['status', 'created_at_after', 'created_at_before']

class LedgerEntryFilter(django_filters.FilterSet):
    created_at_after = django_filters.DateTimeFilter(field_name='create_at', lookup_expr='gte')
    created_at_before = django_filters.DateTimeFilter(field_name='create_at', lookup_expr='lte')
    entry_type = django_filters.ModelChoiceFilter(choices=LedgerEntry.LedgerEntryChoices.choices)

    class Meta:
        model = LedgerEntry
        fields = ['entry_type', 'created_at_after', 'created_at_before']