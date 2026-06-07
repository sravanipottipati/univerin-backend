from django.db import models
import uuid

class Invoice(models.Model):
    INVOICE_TYPES = (
        ('SELLER_TO_BUYER',               'Seller to Buyer'),
        ('PLATFORM_TO_BUYER',             'Platform to Buyer'),
        ('PLATFORM_TO_SELLER_COMMISSION', 'Commission Invoice'),
        ('BUYER_COMBINED_WRAPPER',        'Combined Buyer Invoice'),
        ('SETTLEMENT_STATEMENT',          'Settlement Statement'),
        ('TCS_MONTHLY_STATEMENT',         'TCS Statement'),
        ('CREDIT_NOTE',                   'Credit Note'),
    )
    STATUS_CHOICES = (
        ('DRAFT',     'Draft'),
        ('ISSUED',    'Issued'),
        ('CANCELLED', 'Cancelled'),
    )
    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number          = models.CharField(max_length=30, unique=True)
    invoice_type            = models.CharField(max_length=40, choices=INVOICE_TYPES)
    order                   = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    issuer_name             = models.CharField(max_length=200)
    issuer_gstin            = models.CharField(max_length=15, blank=True, null=True)
    issuer_state            = models.CharField(max_length=100, blank=True, null=True)
    recipient_name          = models.CharField(max_length=200)
    recipient_gstin         = models.CharField(max_length=15, blank=True, null=True)
    recipient_state         = models.CharField(max_length=100, blank=True, null=True)
    place_of_supply         = models.CharField(max_length=100, blank=True, null=True)
    is_interstate           = models.BooleanField(default=False)
    taxable_value           = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cgst                    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst                    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst                    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_value             = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    original_invoice        = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_notes')
    status                  = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ISSUED')
    pdf_url                 = models.TextField(blank=True, null=True)
    fy                      = models.CharField(max_length=4, default='2526')
    issued_at               = models.DateTimeField(auto_now_add=True)
    created_at              = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"{self.invoice_number} ({self.invoice_type})"


class InvoiceLine(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice         = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    line_no         = models.IntegerField()
    description     = models.TextField()
    hsn_or_sac      = models.CharField(max_length=8, blank=True, null=True)
    qty             = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit            = models.CharField(max_length=8, default='nos')
    rate            = models.DecimalField(max_digits=14, decimal_places=2)
    taxable_value   = models.DecimalField(max_digits=14, decimal_places=2)
    gst_rate_pct    = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cgst            = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst            = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst            = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total           = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['line_no']

    def __str__(self):
        return f"{self.invoice.invoice_number} - Line {self.line_no}"


class InvoiceSequence(models.Model):
    """Sequential invoice numbering per series per FY"""
    series  = models.CharField(max_length=20)
    fy      = models.CharField(max_length=4)
    last_no = models.IntegerField(default=0)

    class Meta:
        unique_together = ('series', 'fy')

    @classmethod
    def next_number(cls, series, fy='2526'):
        from django.db import transaction
        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(
                series=series, fy=fy,
                defaults={'last_no': 0}
            )
            obj.last_no += 1
            obj.save()
        return f"{series}/{fy}/{str(obj.last_no).zfill(6)}"

    def __str__(self):
        return f"{self.series}/{self.fy} — {self.last_no}"
