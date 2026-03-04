"""
Module démontage boucherie.

Concepts clés :
- CarcassTemplate : gabarit réutilisable (ex: "Demi-bœuf standard")
- CarcassTemplateLine : pièce attendue dans le gabarit (récursif)
- ButcherySession : session de découpe réelle (une carcasse, un jour)
- ButcheryLine : pièce obtenue lors d'une session (récursif, saisie progressive)
- YieldRecord : historique des rendements par gabarit + fournisseur

Formule prix de revient (méthode coûts joints par prix de vente) :
  PV_HT = PV_TTC / (1 + TVA)
  taux_marge_global = marge_totale / CA_total_HT
  Nouveau_PA(pièce) = PV_HT(pièce) × (1 - taux_marge_global)
"""
from decimal import Decimal
from django.db import models
from django_tenants.utils import get_tenant_model


class CarcassTemplate(models.Model):
    """
    Gabarit de démontage réutilisable.
    Définit les pièces attendues et leurs rendements théoriques.
    """
    SPECIES_CHOICES = [
        ("beef",    "Bœuf"),
        ("veal",    "Veau"),
        ("lamb",    "Agneau"),
        ("pork",    "Porc"),
        ("poultry", "Volaille"),
        ("other",   "Autre"),
    ]

    tenant       = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                                     related_name="carcass_templates")
    name         = models.CharField(max_length=200, verbose_name="Nom du gabarit")
    species      = models.CharField(max_length=20, choices=SPECIES_CHOICES,
                                    verbose_name="Espèce")
    purchase_unit = models.CharField(max_length=100, blank=True,
                                     verbose_name="Unité d'achat",
                                     help_text="Ex: demi-carcasse, quartier arrière, poulet entier")
    description  = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gabarit de démontage"
        ordering = ["species", "name"]

    def __str__(self):
        return f"{self.get_species_display()} — {self.name}"

    def get_total_expected_yield(self):
        """Rendement théorique total = somme des pièces valorisées."""
        return self.lines.filter(
            parent__isnull=True,
            output_type__in=["ingredient", "sellable", "byproduct"]
        ).aggregate(
            total=models.Sum("expected_yield_pct")
        )["total"] or Decimal("0")


class CarcassTemplateLine(models.Model):
    """
    Pièce attendue dans un gabarit — structure récursive infinie.
    Une pièce peut elle-même contenir des sous-pièces.
    Ex: Cuisseau → Noix, Sous-noix, Jarret, Os...
    """
    OUTPUT_CHOICES = [
        ("ingredient", "Ingrédient catalogue"),
        ("sellable",   "Vente directe"),
        ("byproduct",  "Sous-produit valorisable"),
        ("waste",      "Déchet / perte"),
    ]

    template     = models.ForeignKey(CarcassTemplate, on_delete=models.CASCADE,
                                     related_name="lines")
    parent       = models.ForeignKey("self", on_delete=models.CASCADE,
                                     null=True, blank=True,
                                     related_name="children",
                                     verbose_name="Pièce parente")
    name         = models.CharField(max_length=200, verbose_name="Nom de la pièce")
    norm_code    = models.CharField(max_length=20, blank=True,
                                    verbose_name="Code nomenclature",
                                    help_text="Ex: code INTERBEV")
    output_type  = models.CharField(max_length=20, choices=OUTPUT_CHOICES,
                                    default="ingredient",
                                    verbose_name="Destination")
    linked_ingredient = models.ForeignKey(
        "catalog.Ingredient",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="template_lines",
        verbose_name="Ingrédient lié"
    )
    # Prix de vente TTC de référence (pour calcul coûts joints)
    selling_price_ttc = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name="PV TTC de référence (€/kg)",
        help_text="Prix de vente TTC au kg — sert au calcul du prix de revient"
    )
    vat_rate     = models.DecimalField(
        max_digits=5, decimal_places=4,
        default=Decimal("0.055"),
        verbose_name="Taux TVA",
        help_text="Ex: 0.055 pour 5.5%"
    )
    expected_yield_pct = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="Rendement théorique (%)",
        help_text="% du poids de la pièce parente attendu"
    )
    order        = models.PositiveSmallIntegerField(default=0)
    notes        = models.TextField(blank=True)

    class Meta:
        verbose_name = "Ligne gabarit"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    @property
    def selling_price_ht(self):
        if self.selling_price_ttc:
            return self.selling_price_ttc / (1 + self.vat_rate)
        return None

    def get_depth(self):
        """Profondeur dans l'arbre (0 = racine)."""
        depth = 0
        node = self
        while node.parent:
            depth += 1
            node = node.parent
        return depth


class ButcherySession(models.Model):
    """
    Session de découpe réelle — une carcasse, un jour, un boucher.
    Reste ouverte tant que la découpe n'est pas terminée.
    Les prix de revient sont calculés à la clôture.
    """
    STATUS_CHOICES = [
        ("open",      "En cours"),
        ("completed", "Terminée — en attente de calcul"),
        ("validated", "Validée — prix calculés"),
    ]
    SPECIES_CHOICES = CarcassTemplate.SPECIES_CHOICES

    tenant       = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                                     related_name="butchery_sessions")
    template     = models.ForeignKey(CarcassTemplate, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     verbose_name="Gabarit utilisé")
    # Lien optionnel vers le BL d'achat
    delivery_line = models.ForeignKey(
        "purchasing.DeliveryLine",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="butchery_sessions",
        verbose_name="Ligne BL d'achat"
    )

    # Description de la carcasse
    description  = models.CharField(max_length=200,
                                    verbose_name="Description",
                                    help_text="Ex: Demi-bœuf Charolaise n°47 — SCA Le Pré Vert")
    species      = models.CharField(max_length=20, choices=SPECIES_CHOICES,
                                    verbose_name="Espèce")
    session_date = models.DateField(verbose_name="Date de découpe")
    butcher      = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Boucher"
    )
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                    default="open")

    # Prix d'achat (depuis BL ou saisi manuellement)
    purchase_weight_kg    = models.DecimalField(
        max_digits=8, decimal_places=3,
        verbose_name="Poids à l'achat (kg)"
    )
    purchase_price_per_kg = models.DecimalField(
        max_digits=8, decimal_places=4,
        verbose_name="Prix d'achat (€/kg HT)"
    )
    purchase_total_ht     = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Coût achat total HT (€)"
    )
    # Taxes filière (CVO, INTERBEV...) depuis le BL
    sector_tax_total_ht   = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=Decimal("0"),
        verbose_name="Taxes filière HT (€)"
    )
    # Prestation externe (désossage, mise sous vide...)
    processing_cost_ht    = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=Decimal("0"),
        verbose_name="Prestation externe HT (€)",
        help_text="Désossage, mise sous vide, etc."
    )

    # Résultats calculés à la clôture
    total_output_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3,
        null=True, blank=True,
        verbose_name="Poids total valorisé (kg)"
    )
    total_waste_kg         = models.DecimalField(
        max_digits=8, decimal_places=3,
        null=True, blank=True,
        verbose_name="Poids pertes/déchets (kg)"
    )
    real_yield_pct         = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="Rendement réel (%)"
    )
    # KPI global
    avg_cost_per_kg        = models.DecimalField(
        max_digits=8, decimal_places=4,
        null=True, blank=True,
        verbose_name="Coût moyen brut (€/kg valorisé)",
        help_text="Coût total / poids valorisé — info comparative"
    )
    global_margin_rate     = models.DecimalField(
        max_digits=6, decimal_places=4,
        null=True, blank=True,
        verbose_name="Taux de marge global réalisé"
    )

    notes        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Session de découpe"
        ordering = ["-session_date", "-created_at"]

    def __str__(self):
        return f"{self.description} ({self.session_date})"

    @property
    def total_cost_ht(self):
        """Coût total = achat + taxes filière + prestation externe."""
        return (
            self.purchase_total_ht
            + self.sector_tax_total_ht
            + self.processing_cost_ht
        )

    def get_lines_summary(self):
        """Résumé rapide des lignes pour l'affichage."""
        return {
            "total":     self.lines.count(),
            "confirmed": self.lines.filter(is_confirmed=True).count(),
            "waste":     self.lines.filter(output_type="waste").count(),
        }


class ButcheryLine(models.Model):
    """
    Pièce obtenue lors d'une session — saisie progressive par le boucher.
    Structure récursive : une pièce intermédiaire peut être re-découpée.

    Ex: Cuisseau pesé → re-découpé en Noix + Sous-noix + Jarret + Os
    """
    OUTPUT_CHOICES = [
        ("ingredient", "Ingrédient catalogue"),
        ("sellable",   "Vente directe"),
        ("byproduct",  "Sous-produit valorisable"),
        ("waste",      "Déchet / perte"),
        ("processing", "En cours de découpe"),  # pièce intermédiaire
    ]

    session      = models.ForeignKey(ButcherySession, on_delete=models.CASCADE,
                                     related_name="lines")
    parent_line  = models.ForeignKey("self", on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name="sub_lines",
                                     verbose_name="Pièce parente")
    template_line = models.ForeignKey(CarcassTemplateLine, on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      verbose_name="Ligne gabarit")

    name         = models.CharField(max_length=200, verbose_name="Nom de la pièce")
    output_type  = models.CharField(max_length=20, choices=OUTPUT_CHOICES,
                                    default="ingredient",
                                    verbose_name="Destination")

    # Poids réel mesuré sur la balance
    real_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3,
        verbose_name="Poids réel (kg)"
    )

    # Lien catalogue
    linked_ingredient = models.ForeignKey(
        "catalog.Ingredient",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="butchery_lines",
        verbose_name="Ingrédient lié"
    )

    # Prix de vente TTC saisi pour cette pièce (peut différer du gabarit)
    selling_price_ttc = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name="PV TTC (€/kg)"
    )
    vat_rate     = models.DecimalField(
        max_digits=5, decimal_places=4,
        default=Decimal("0.055"),
        verbose_name="Taux TVA"
    )

    # Calculé à la clôture de la session
    cost_per_kg  = models.DecimalField(
        max_digits=8, decimal_places=4,
        null=True, blank=True,
        verbose_name="Prix de revient (€/kg)"
    )
    total_cost   = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Coût total (€)"
    )
    theoretical_ca = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="CA théorique (€)"
    )

    # Sous-produit
    byproduct_selling_price = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name="PV sous-produit (€/kg)"
    )
    byproduct_sold = models.BooleanField(default=False,
                                         verbose_name="Sous-produit vendu")

    is_confirmed = models.BooleanField(default=False,
                                       verbose_name="Pesée confirmée")
    order        = models.PositiveSmallIntegerField(default=0)
    notes        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ligne de découpe"
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"{self.name} — {self.real_weight_kg}kg"

    @property
    def selling_price_ht(self):
        if self.selling_price_ttc:
            return self.selling_price_ttc / (1 + self.vat_rate)
        return None

    @property
    def ca_theorique(self):
        if self.selling_price_ttc and self.real_weight_kg:
            return self.selling_price_ttc * self.real_weight_kg
        return None

    def has_sub_lines(self):
        return self.sub_lines.exists()


class YieldRecord(models.Model):
    """
    Historique des rendements réels — une entrée par session clôturée.
    Permet de comparer les fournisseurs sur la durée.
    """
    session      = models.OneToOneField(ButcherySession, on_delete=models.CASCADE,
                                        related_name="yield_record")
    template     = models.ForeignKey(CarcassTemplate, on_delete=models.SET_NULL,
                                     null=True, blank=True)
    supplier     = models.ForeignKey("purchasing.Supplier", on_delete=models.SET_NULL,
                                     null=True, blank=True)
    session_date = models.DateField()

    purchase_weight_kg    = models.DecimalField(max_digits=8, decimal_places=3)
    purchase_price_per_kg = models.DecimalField(max_digits=8, decimal_places=4)
    total_cost_ht         = models.DecimalField(max_digits=10, decimal_places=2)

    # Rendements
    global_yield_pct      = models.DecimalField(max_digits=6, decimal_places=2)
    waste_pct             = models.DecimalField(max_digits=6, decimal_places=2)
    effective_cost_per_kg = models.DecimalField(max_digits=8, decimal_places=4,
                                                verbose_name="Coût réel/kg valorisé")
    global_margin_rate    = models.DecimalField(max_digits=6, decimal_places=4)

    # Détail par pièce (JSON pour flexibilité)
    yields_data  = models.JSONField(default=dict,
                                    help_text="Détail rendements par pièce")

    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Historique rendement"
        ordering = ["-session_date"]

    def __str__(self):
        return f"{self.template} — {self.session_date} — {self.global_yield_pct}%"