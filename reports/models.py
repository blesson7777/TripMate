from django.db import models


class TransporterBillRecipient(models.Model):
    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="bill_recipients",
    )
    name = models.CharField(max_length=255)
    address = models.TextField(help_text="Multi-line address")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "-updated_at"]
        indexes = [
            models.Index(fields=["transporter", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}"


class TransporterBankDetails(models.Model):
    transporter = models.OneToOneField(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="bank_details",
    )
    bank_name = models.CharField(max_length=120, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    account_no = models.CharField(max_length=64, blank=True)
    ifsc_code = models.CharField(max_length=32, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.transporter.company_name} bank details"


class TransporterBillHeaderDetails(models.Model):
    transporter = models.OneToOneField(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="bill_header_details",
    )
    company_name = models.CharField(max_length=255, blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=32, blank=True)
    pan = models.CharField(max_length=32, blank=True)
    website = models.CharField(max_length=120, blank=True)
    biller_name = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.transporter.company_name} bill header"


class TransporterVehicleBill(models.Model):
    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="vehicle_bills",
    )
    recipient = models.ForeignKey(
        "reports.TransporterBillRecipient",
        on_delete=models.SET_NULL,
        related_name="vehicle_bills",
        null=True,
        blank=True,
    )

    bill_no = models.CharField(max_length=40, blank=True)
    bill_date = models.DateField(null=True, blank=True)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)

    vehicle_number = models.CharField(max_length=40)
    service_name = models.CharField(max_length=255, blank=True)

    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    extra_km = models.PositiveIntegerField(default=0)
    extra_rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    to_name = models.CharField(max_length=255)
    to_address = models.TextField()

    bank_name = models.CharField(max_length=120, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    account_no = models.CharField(max_length=64, blank=True)
    ifsc_code = models.CharField(max_length=32, blank=True)

    from_company_name = models.CharField(max_length=255, blank=True)
    from_contact_name = models.CharField(max_length=255, blank=True)
    from_phone = models.CharField(max_length=32, blank=True)
    from_email = models.EmailField(blank=True)
    from_gstin = models.CharField(max_length=32, blank=True)
    from_pan = models.CharField(max_length=32, blank=True)
    from_website = models.CharField(max_length=120, blank=True)
    biller_name = models.CharField(max_length=255, blank=True)

    pdf_file = models.FileField(upload_to="vehicle_bills/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transporter", "created_at"]),
            models.Index(fields=["transporter", "bill_no"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["transporter", "bill_no"],
                name="unique_transporter_vehicle_bill_no",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bill_no or 'Vehicle Bill'} ({self.vehicle_number})"
