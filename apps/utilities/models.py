from django.db import models


class Allergen(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name="Allergène")

    class Meta:
        verbose_name = "Allergène"
        verbose_name_plural = "Allergènes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class VatRate(models.Model):
    name = models.CharField(max_length=60, verbose_name="Libellé")
    rate = models.DecimalField(max_digits=5, decimal_places=4, verbose_name="Taux")
    # ex: 0.055 pour 5.5%, 0.10 pour 10%, 0.20 pour 20%

    class Meta:
        verbose_name = "Taux de TVA"
        verbose_name_plural = "Taux de TVA"
        ordering = ["rate"]

    def __str__(self):
        return f"{self.name} ({self.rate * 100:.1f}%)"


class Unit(models.Model):
    """
    Unités de mesure disponibles dans tout le système.
    Centralisées ici pour éviter les CharField avec choices éparpillés.
    """
    UNIT_TYPES = [
        ("weight", "Poids"),
        ("volume", "Volume"),
        ("piece", "Pièce/Conditionnement"),
    ]
    name = models.CharField(max_length=20, unique=True, verbose_name="Unité")
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES, verbose_name="Type")
    symbol = models.CharField(max_length=10, verbose_name="Symbole")

    class Meta:
        verbose_name = "Unité"
        verbose_name_plural = "Unités"
        ordering = ["unit_type", "name"]

    def __str__(self):
        return self.symbol