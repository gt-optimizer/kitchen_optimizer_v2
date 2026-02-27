"""
Management command : import du fichier XLSX CIQUAL 2025 ANSES.

Usage :
  python manage.py import_ciqual /path/to/Table_Ciqual_2025_FR.xlsx
  python manage.py import_ciqual /path/to/Table_Ciqual_2025_FR.xlsx --clear

Le fichier XLSX 2025 a des en-têtes avec des sauts de ligne (\n).
Les valeurs manquantes sont None, '-', ou vides.
Les valeurs traces sont des floats directs (pas de '< X' en xlsx).
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from apps.ciqual.models import CiqualIngredient


def normalize_header(h):
    """Normalise un header xlsx : supprime les \n et espaces multiples."""
    if h is None:
        return ""
    return " ".join(str(h).split())


def parse_value(value):
    """Convertit une valeur CIQUAL en float ou None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s in ("-", "", "nd", "ND"):
        return None
    # Valeur trace : '< X'
    import re
    match = re.match(r"<\s*([\d,\.]+)", s)
    if match:
        s = match.group(1)
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# Mapping headers normalisés → champs modèle
# Clé = header xlsx normalisé (sans \n), valeur = champ Django
COLUMN_MAP = {
    "alim_grp_nom_fr":                                              "group",
    "alim_ssgrp_nom_fr":                                            "sub_group",
    "alim_code":                                                    "ciqual_code",
    "alim_nom_fr":                                                  "name_fr",
    "alim_nom_sci":                                                 "name_en",
    "Energie, Reglement UE N° 1169 2011 (kJ 100 g)":               "energy_kj",
    "Energie, Reglement UE N° 1169 2011 (kcal 100 g)":             "energy_kcal",
    "Eau (g 100 g)":                                                "water",
    "Proteines, N x facteur de Jones (g 100 g)":                   "protein",
    "Glucides (g 100 g)":                                           "carbohydrates",
    "Lipides (g 100 g)":                                            "fat",
    "Sucres (g 100 g)":                                             "sugars",
    "AG satures (g 100 g)":                                         "saturates",
    "Fibres alimentaires (g 100 g)":                                "fiber",
    "Sel chlorure de sodium (g 100 g)":                             "salt",
    "Sodium (mg 100 g)":                                            "sodium",
    "Calcium (mg 100 g)":                                           "calcium",
    "Fer (mg 100 g)":                                               "iron",
    "Vitamine C (mg 100 g)":                                        "vitamin_c",
    "Vitamine D (µg 100 g)":                                        "vitamin_d",
}

NUMERIC_FIELDS = {
    "energy_kj", "energy_kcal", "water", "protein", "carbohydrates",
    "fat", "sugars", "saturates", "fiber", "salt",
    "sodium", "calcium", "iron", "vitamin_c", "vitamin_d",
}


def normalize_for_match(s):
    """Normalise pour comparaison : minuscules, supprime accents."""
    import unicodedata
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s


class Command(BaseCommand):
    help = "Importe le fichier XLSX CIQUAL 2025 ANSES dans la table CiqualIngredient"

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str, help="Chemin vers le fichier XLSX CIQUAL")
        parser.add_argument(
            "--clear", action="store_true",
            help="Vide la table CiqualIngredient avant l'import"
        )

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("openpyxl requis : pip install openpyxl --break-system-packages")

        xlsx_path = Path(options["xlsx_path"])
        if not xlsx_path.exists():
            raise CommandError(f"Fichier introuvable : {xlsx_path}")

        self.stdout.write(f"Chargement de {xlsx_path.name}...")
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active

        rows = ws.iter_rows(values_only=True)
        raw_headers = next(rows)

        # Normalise les headers et construit l'index colonne
        headers = [normalize_header(h) for h in raw_headers]

        # Construit un mapping index_colonne → champ_modèle
        col_to_field = {}
        for col_idx, header in enumerate(headers):
            header_norm = normalize_for_match(header)
            for map_key, field in COLUMN_MAP.items():
                if normalize_for_match(map_key) == header_norm:
                    col_to_field[col_idx] = field
                    break

        self.stdout.write(f"Colonnes mappées : {len(col_to_field)} / {len(COLUMN_MAP)}")

        # Vérifie que alim_code et alim_nom_fr sont trouvés
        mapped_fields = set(col_to_field.values())
        for required in ("ciqual_code", "name_fr"):
            if required not in mapped_fields:
                raise CommandError(
                    f"Colonne obligatoire '{required}' non trouvée. "
                    f"Headers disponibles : {headers[:10]}"
                )

        with schema_context("public"):
            if options["clear"]:
                count = CiqualIngredient.objects.count()
                CiqualIngredient.objects.all().delete()
                self.stdout.write(self.style.WARNING(f"{count} entrées supprimées."))

            created = updated = errors = skipped = 0
            batch = []
            BATCH_SIZE = 200

            for row_num, row in enumerate(rows, start=2):
                try:
                    data = {}
                    for col_idx, field in col_to_field.items():
                        value = row[col_idx] if col_idx < len(row) else None
                        if field in NUMERIC_FIELDS:
                            data[field] = parse_value(value)
                        else:
                            data[field] = str(value).strip() if value is not None else ""

                    code = data.get("ciqual_code", "")
                    if not code or code == "-":
                        skipped += 1
                        continue

                    batch.append(data)

                    if len(batch) >= BATCH_SIZE:
                        c, u = self._flush_batch(batch)
                        created += c
                        updated += u
                        batch = []
                        self.stdout.write(f"  {created + updated} traités...")

                except Exception as e:
                    errors += 1
                    self.stderr.write(f"Ligne {row_num} : {e}")

            # Dernier batch
            if batch:
                c, u = self._flush_batch(batch)
                created += c
                updated += u

        wb.close()
        self.stdout.write(self.style.SUCCESS(
            f"\nImport terminé : {created} créés, {updated} mis à jour, "
            f"{skipped} ignorés, {errors} erreurs."
        ))

    def _flush_batch(self, batch):
        """Traite un batch de lignes avec update_or_create."""
        created = updated = 0
        for data in batch:
            code = data.pop("ciqual_code")
            _, was_created = CiqualIngredient.objects.update_or_create(
                ciqual_code=code,
                defaults=data,
            )
            if was_created:
                created += 1
            else:
                updated += 1
        return created, updated