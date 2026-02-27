"""
apps/pms/models.py — Plan de Maîtrise Sanitaire

Sous-modules :
  1. Nettoyage      : CleaningZone, CleaningSchedule, CleaningRecord
  2. Températures   : StorageUnit, TemperatureLog, CookingLog, ThawingLog, CoolingLog
  3. Transferts     : InternalTransfer, TransferLog
"""
from django.db import models
from django.utils.timezone import now
from django.core.exceptions import ValidationError

from apps.company.models import Company, Employee
from apps.users.models import User
from apps.catalog.models import Recipe
from apps.production.models import ProductionRecord


# ══════════════════════════════════════════════════════════════════════════════
# 1. NETTOYAGE
# ══════════════════════════════════════════════════════════════════════════════

class CleaningZone(models.Model):
    """
    Surface ou équipement à nettoyer.
    Ex: Plan de travail boucher, Four à sole, Sol chambre froide...
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="cleaning_zones")
    name = models.CharField(max_length=100, verbose_name="Nom")
    location = models.CharField(max_length=100, blank=True, verbose_name="Localisation")
    cleaning_product = models.CharField(max_length=100, blank=True, verbose_name="Produit nettoyant")
    disinfection_product = models.CharField(max_length=100, blank=True, verbose_name="Produit désinfectant")
    procedure = models.TextField(blank=True, verbose_name="Procédure")
    reference_document = models.CharField(
        max_length=200, blank=True,
        verbose_name="Référence document PMS",
        help_text="Réservé pour future intégration RAG/bibliothèque PMS"
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        verbose_name = "Zone / Surface à nettoyer"
        verbose_name_plural = "Zones / Surfaces à nettoyer"
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class CleaningSchedule(models.Model):
    """
    Fréquence et créneau de nettoyage pour une zone.

    Fréquences supportées :
      - after_use    : après chaque utilisation
      - daily        : tous les jours
      - weekly       : hebdomadaire (ex: tous les mardis)
      - biweekly     : bihebdomadaire (semaines paires ou impaires)
      - monthly      : mensuel (ex: 2ème semaine du mois)
      - annual       : annuel (ex: semaine 26)

    Le créneau est soit une heure fixe, soit un libellé ordonné
    (ex: "avant ouverture", "pause repas", "après fermeture").
    """
    FREQUENCY_CHOICES = [
        ("after_use", "Après chaque utilisation"),
        ("daily", "Quotidien"),
        ("weekly", "Hebdomadaire"),
        ("biweekly", "Bihebdomadaire"),
        ("monthly", "Mensuel"),
        ("annual", "Annuel"),
    ]

    WEEK_PARITY_CHOICES = [
        ("odd", "Semaines impaires"),
        ("even", "Semaines paires"),
    ]

    WEEKDAY_CHOICES = [
        (0, "Lundi"), (1, "Mardi"), (2, "Mercredi"),
        (3, "Jeudi"), (4, "Vendredi"), (5, "Samedi"), (6, "Dimanche"),
    ]

    zone = models.ForeignKey(CleaningZone, on_delete=models.CASCADE, related_name="schedules")
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, verbose_name="Fréquence")

    # Hebdomadaire / bihebdomadaire
    weekday = models.PositiveSmallIntegerField(
        choices=WEEKDAY_CHOICES, null=True, blank=True, verbose_name="Jour de la semaine"
    )
    week_parity = models.CharField(
        max_length=4, choices=WEEK_PARITY_CHOICES,
        null=True, blank=True, verbose_name="Parité semaine"
    )

    # Mensuel
    week_of_month = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Semaine du mois (1-4)",
        help_text="Ex: 2 pour la 2ème semaine du mois"
    )

    # Annuel
    week_of_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Semaine de l'année (1-52)"
    )

    # Créneau horaire
    time_slot_label = models.CharField(
        max_length=60, blank=True, verbose_name="Libellé créneau",
        help_text="Ex: Avant ouverture, Pause repas, Après fermeture"
    )
    time_slot_order = models.PositiveSmallIntegerField(
        default=1, verbose_name="Ordre du créneau",
        help_text="Pour trier les créneaux dans la journée"
    )
    time_slot_hour = models.TimeField(
        null=True, blank=True, verbose_name="Heure fixe",
        help_text="Si vide, utiliser le libellé créneau"
    )

    class Meta:
        verbose_name = "Planning de nettoyage"
        verbose_name_plural = "Plannings de nettoyage"
        ordering = ["zone", "time_slot_order"]

    def __str__(self):
        return f"{self.zone.name} — {self.get_frequency_display()} ({self.time_slot_label or self.time_slot_hour})"


class CleaningRecord(models.Model):
    """
    Enregistrement d'un nettoyage effectué.

    Deux modes de signature :
      - Mode 1 (user individuel) : signed_by_user est renseigné
      - Mode 2 (user commun TPE) : signed_by_employee est renseigné
    L'un ou l'autre, jamais les deux, jamais aucun.
    """
    zone = models.ForeignKey(CleaningZone, on_delete=models.PROTECT, related_name="records")
    schedule = models.ForeignKey(
        CleaningSchedule, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Planning associé"
    )
    done_at = models.DateTimeField(default=now, verbose_name="Effectué le")

    # Signature mode 1 : user individuel
    signed_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cleaning_records",
        verbose_name="Utilisateur"
    )
    # Signature mode 2 : sélection employé sur user commun
    signed_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cleaning_records",
        verbose_name="Employé"
    )

    is_compliant = models.BooleanField(default=True, verbose_name="Conforme")
    anomaly_and_action = models.TextField(
        blank=True, verbose_name="Anomalie constatée & action corrective"
    )

    class Meta:
        verbose_name = "Enregistrement nettoyage"
        verbose_name_plural = "Enregistrements nettoyage"
        ordering = ["-done_at"]

    def clean(self):
        has_user = self.signed_by_user_id is not None
        has_employee = self.signed_by_employee_id is not None
        if has_user and has_employee:
            raise ValidationError("Un seul signataire : user OU employé, pas les deux.")
        if not has_user and not has_employee:
            raise ValidationError("Un signataire est obligatoire.")

    def __str__(self):
        signer = self.signed_by_user or self.signed_by_employee
        return f"{self.zone.name} — {self.done_at:%d/%m/%Y %H:%M} par {signer}"


# ══════════════════════════════════════════════════════════════════════════════
# 2. TEMPÉRATURES
# ══════════════════════════════════════════════════════════════════════════════

class StorageUnit(models.Model):
    """
    Enceinte froide à surveiller (frigo, congélateur, chambre froide...).
    """
    UNIT_TYPE_CHOICES = [
        ("fridge", "Réfrigérateur"),
        ("freezer", "Congélateur"),
        ("cold_room", "Chambre froide positive"),
        ("frozen_room", "Chambre froide négative"),
        ("display", "Vitrine réfrigérée"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="storage_units")
    name = models.CharField(max_length=100, verbose_name="Nom")
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPE_CHOICES, verbose_name="Type")

    # Seuils configurables par le client
    temp_min = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° minimale (°C)"
    )
    temp_max = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° maximale (°C)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        verbose_name = "Enceinte froide"
        verbose_name_plural = "Enceintes froides"
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} ({self.company.name})"

    @property
    def threshold_display(self):
        if self.temp_min is not None and self.temp_max is not None:
            return f"{self.temp_min}°C < T° < {self.temp_max}°C"
        if self.temp_min is not None:
            return f"T° > {self.temp_min}°C"
        if self.temp_max is not None:
            return f"T° < {self.temp_max}°C"
        return "Pas de seuil défini"


class TemperatureLog(models.Model):
    """
    Relevé de température d'une enceinte froide.
    """
    storage_unit = models.ForeignKey(StorageUnit, on_delete=models.PROTECT, related_name="logs")
    recorded_at = models.DateTimeField(default=now, verbose_name="Relevé le")
    temperature = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Température (°C)")

    signed_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="temperature_logs"
    )
    signed_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="temperature_logs"
    )

    is_compliant = models.BooleanField(default=True, verbose_name="Conforme")
    anomaly_and_action = models.TextField(blank=True, verbose_name="Anomalie & action corrective")

    class Meta:
        verbose_name = "Relevé de température"
        verbose_name_plural = "Relevés de température"
        ordering = ["-recorded_at"]

    def save(self, *args, **kwargs):
        # Calcul automatique de la conformité si seuils définis
        unit = self.storage_unit
        if unit.temp_min is not None or unit.temp_max is not None:
            above_min = (unit.temp_min is None) or (self.temperature >= unit.temp_min)
            below_max = (unit.temp_max is None) or (self.temperature <= unit.temp_max)
            self.is_compliant = above_min and below_max
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.storage_unit.name} — {self.recorded_at:%d/%m/%Y %H:%M} : {self.temperature}°C"


class CookingLog(models.Model):
    """
    Relevé de température de fin de cuisson.
    La température cible est définie sur la recette (définie par article).

    Pour les cuissons longues (stérilisation) : couple temps + température.
    """
    production_record = models.ForeignKey(
        ProductionRecord, on_delete=models.CASCADE,
        related_name="cooking_logs", verbose_name="Production associée"
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.PROTECT,
        verbose_name="Recette / Article"
    )

    # Température cible (copiée depuis la recette au moment de l'enregistrement)
    target_temp = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° cible (°C)"
    )
    measured_temp = models.DecimalField(
        max_digits=5, decimal_places=2,
        verbose_name="T° mesurée (°C)"
    )

    # Couple temps / température pour stérilisation (optionnel)
    cooking_duration_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Durée de cuisson (min)",
        help_text="Pour les cuissons longues : couple temps/température"
    )

    recorded_at = models.DateTimeField(default=now, verbose_name="Relevé le")
    signed_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cooking_logs"
    )
    signed_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cooking_logs"
    )

    is_compliant = models.BooleanField(default=True, verbose_name="Conforme")
    anomaly_and_action = models.TextField(blank=True, verbose_name="Anomalie & action corrective")

    class Meta:
        verbose_name = "Relevé de cuisson"
        verbose_name_plural = "Relevés de cuisson"
        ordering = ["-recorded_at"]

    def save(self, *args, **kwargs):
        if self.target_temp is not None:
            self.is_compliant = self.measured_temp >= self.target_temp
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.recipe.name} — {self.measured_temp}°C ({self.recorded_at:%d/%m/%Y})"


class ThawingLog(models.Model):
    """
    Enregistrement d'un processus de décongélation.
    """
    METHOD_CHOICES = [
        ("immediate_cooking", "Cuisson immédiate"),
        ("fridge_24h", "Décongélation au réfrigérateur (24h)"),
        ("fridge_48h", "Décongélation au réfrigérateur (48h)"),
        ("other", "Autre méthode"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="thawing_logs")
    product_name = models.CharField(max_length=100, verbose_name="Produit décongelé")
    quantity = models.DecimalField(max_digits=8, decimal_places=3, verbose_name="Quantité")
    unit = models.CharField(max_length=10, verbose_name="Unité")

    started_at = models.DateTimeField(default=now, verbose_name="Heure de sortie du congélateur")
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, verbose_name="Méthode")
    other_method_description = models.CharField(
        max_length=200, blank=True, verbose_name="Autre méthode (préciser)"
    )

    signed_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="thawing_logs"
    )
    signed_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="thawing_logs"
    )

    anomaly_and_action = models.TextField(blank=True, verbose_name="Anomalie & action corrective")

    class Meta:
        verbose_name = "Enregistrement décongélation"
        verbose_name_plural = "Enregistrements décongélation"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.product_name} — {self.started_at:%d/%m/%Y %H:%M} ({self.get_method_display()})"


class CoolingLog(models.Model):
    """
    Enregistrement du refroidissement rapide en cellule.
    Couple temps/température pour garantir la descente en température.
    Réglementation : +63°C → +10°C en moins de 2h, +10°C → +3°C en moins de 2h.
    """
    production_record = models.ForeignKey(
        ProductionRecord, on_delete=models.CASCADE,
        related_name="cooling_logs", verbose_name="Production associée"
    )
    start_temp = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="T° en entrée cellule (°C)"
    )
    end_temp = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="T° en sortie cellule (°C)"
    )
    duration_minutes = models.PositiveIntegerField(verbose_name="Durée (min)")
    target_end_temp = models.DecimalField(
        max_digits=5, decimal_places=2, default=3,
        verbose_name="T° cible en sortie (°C)"
    )
    recorded_at = models.DateTimeField(default=now, verbose_name="Relevé le")

    signed_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cooling_logs"
    )
    signed_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cooling_logs"
    )

    is_compliant = models.BooleanField(default=True, verbose_name="Conforme")
    anomaly_and_action = models.TextField(blank=True, verbose_name="Anomalie & action corrective")

    class Meta:
        verbose_name = "Enregistrement refroidissement"
        verbose_name_plural = "Enregistrements refroidissement"
        ordering = ["-recorded_at"]

    def save(self, *args, **kwargs):
        self.is_compliant = self.end_temp <= self.target_end_temp
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.production_record.recipe.name} — "
            f"{self.start_temp}°C → {self.end_temp}°C en {self.duration_minutes} min"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3. TRANSFERTS INTER-SITES
# ══════════════════════════════════════════════════════════════════════════════

class InternalTransfer(models.Model):
    """
    Transfert de produits entre deux sites du même tenant.
    Ex: Boucherie A envoie des saucisses crues à Boucherie B.
    """
    from_company = models.ForeignKey(
        Company, on_delete=models.PROTECT,
        related_name="outgoing_transfers", verbose_name="Site expéditeur"
    )
    to_company = models.ForeignKey(
        Company, on_delete=models.PROTECT,
        related_name="incoming_transfers", verbose_name="Site destinataire"
    )
    transferred_at = models.DateTimeField(default=now, verbose_name="Date / heure départ")
    received_at = models.DateTimeField(null=True, blank=True, verbose_name="Date / heure réception")

    notes = models.TextField(blank=True, verbose_name="Notes")

    # Signataires départ
    sent_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="sent_transfers"
    )
    sent_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="sent_transfers"
    )

    # Signataires arrivée
    received_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True, related_name="received_transfers"
    )
    received_by_employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        null=True, blank=True, related_name="received_transfers"
    )

    class Meta:
        verbose_name = "Transfert interne"
        verbose_name_plural = "Transferts internes"
        ordering = ["-transferred_at"]

    def clean(self):
        if self.from_company_id == self.to_company_id:
            raise ValidationError("Le site expéditeur et le site destinataire doivent être différents.")

    def __str__(self):
        return f"{self.from_company.name} → {self.to_company.name} ({self.transferred_at:%d/%m/%Y %H:%M})"


class InternalTransferLine(models.Model):
    """
    Ligne d'un transfert : quel produit, quelle quantité, quel lot de production.
    """
    transfer = models.ForeignKey(InternalTransfer, on_delete=models.CASCADE, related_name="lines")
    production_record = models.ForeignKey(
        ProductionRecord, on_delete=models.PROTECT,
        verbose_name="Lot de production transféré"
    )
    quantity = models.DecimalField(max_digits=8, decimal_places=3, verbose_name="Quantité")
    unit = models.CharField(max_length=10, verbose_name="Unité")

    # T° au départ
    temp_at_departure = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° au départ (°C)"
    )
    # T° à l'arrivée
    temp_at_arrival = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° à l'arrivée (°C)"
    )

    # Seuil de conformité pour ce produit au transport
    temp_max_transport = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° maximale transport (°C)"
    )

    is_compliant = models.BooleanField(default=True, verbose_name="Conforme")
    anomaly_and_action = models.TextField(blank=True, verbose_name="Anomalie & action corrective")

    class Meta:
        verbose_name = "Ligne de transfert"
        verbose_name_plural = "Lignes de transfert"

    def save(self, *args, **kwargs):
        if self.temp_at_arrival is not None and self.temp_max_transport is not None:
            self.is_compliant = self.temp_at_arrival <= self.temp_max_transport
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.production_record.recipe.name} × {self.quantity} ({self.transfer})"