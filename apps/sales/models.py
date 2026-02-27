from django.db import models

# Create your models here.
from django.db import models
from django.utils.timezone import now

from apps.company.models import Company


class SalesImport(models.Model):
    """
    Import brut d'un fichier CA depuis un logiciel de caisse.
    On conserve le fichier original pour retraitement éventuel.
    """
    class ImportFormat(models.TextChoices):
        CSV = "csv", "CSV générique"
        ZELTY = "zelty", "Zelty"
        LIGHTSPEED = "lightspeed", "Lightspeed"
        SUMUP = "sumup", "SumUp"
        OTHER = "other", "Autre"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sales_imports")
    imported_at = models.DateTimeField(auto_now_add=True, verbose_name="Importé le")
    import_format = models.CharField(
        max_length=20, choices=ImportFormat.choices,
        default=ImportFormat.CSV, verbose_name="Format"
    )
    source_file = models.FileField(
        upload_to="sales/imports/", verbose_name="Fichier source"
    )
    period_start = models.DateField(verbose_name="Début de période")
    period_end = models.DateField(verbose_name="Fin de période")
    is_processed = models.BooleanField(default=False, verbose_name="Traité")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Import CA"
        verbose_name_plural = "Imports CA"
        ordering = ["-imported_at"]

    def __str__(self):
        return f"Import {self.company.name} — {self.period_start} → {self.period_end}"


class DailySales(models.Model):
    """
    CA journalier — une ligne par jour par site.
    Alimenté par SalesImport ou saisi manuellement.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="daily_sales")
    date = models.DateField(verbose_name="Date")
    revenue_ttc = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="CA TTC"
    )
    revenue_ht = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="CA HT"
    )
    covers = models.PositiveIntegerField(
        default=0, verbose_name="Nombre de couverts / tickets"
    )
    source = models.ForeignKey(
        SalesImport, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Source d'import"
    )
    is_closed = models.BooleanField(
        default=False, verbose_name="Journée clôturée",
        help_text="Une journée clôturée ne peut plus être modifiée"
    )

    class Meta:
        verbose_name = "CA journalier"
        verbose_name_plural = "CA journaliers"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "date"],
                name="unique_daily_sales_per_company"
            )
        ]

    def __str__(self):
        return f"{self.company.name} — {self.date} : {self.revenue_ttc}€ TTC"

    @property
    def average_basket(self):
        """Panier moyen."""
        if self.covers and self.covers > 0:
            return round(self.revenue_ttc / self.covers, 2)
        return 0


class SalesForecast(models.Model):
    """
    Prévision de CA — générée par le moteur de prévision.
    Stocke la prévision ET la réalité pour mesurer la précision du modèle.
    """
    class ForecastMethod(models.TextChoices):
        LINEAR = "linear", "Régression linéaire"
        MOVING_AVG = "moving_avg", "Moyenne mobile"
        SEASONAL = "seasonal", "Saisonnalité N-1"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="forecasts")
    date = models.DateField(verbose_name="Date prévue")
    forecasted_revenue = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="CA prévu TTC"
    )
    actual_revenue = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True, verbose_name="CA réel TTC"
    )
    method = models.CharField(
        max_length=20, choices=ForecastMethod.choices,
        default=ForecastMethod.SEASONAL, verbose_name="Méthode"
    )
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name="Généré le")
    week_number = models.PositiveSmallIntegerField(verbose_name="Numéro de semaine")
    year = models.PositiveSmallIntegerField(verbose_name="Année")

    class Meta:
        verbose_name = "Prévision CA"
        verbose_name_plural = "Prévisions CA"
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "date", "method"],
                name="unique_forecast_per_day_per_method"
            )
        ]

    def __str__(self):
        return f"Prévision {self.company.name} — {self.date} : {self.forecasted_revenue}€"

    @property
    def accuracy(self):
        """Écart entre prévu et réel en %."""
        if self.actual_revenue and self.actual_revenue > 0:
            return round(
                abs(self.forecasted_revenue - self.actual_revenue) / self.actual_revenue * 100, 2
            )
        return None

    def save(self, *args, **kwargs):
        self.week_number = self.date.isocalendar()[1]
        self.year = self.date.year
        super().save(*args, **kwargs)
