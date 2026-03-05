# L'Atelier — Journal de développement

## Stack technique
- Python 3.12, Django 5.2, django-tenants
- PostgreSQL (schemas séparés par tenant)
- HTMX + Alpine.js + Bootstrap 5 + FontAwesome 7
- Tesseract OCR + Mistral Vision (fallback)
- Whitenoise (static files)
- Mistral Small (LLM parsing OCR BL/factures)
- rapidfuzz (matching fuzzy ingrédients)

## Structure projet
```
kitchen_optimizer_v2/
  apps/
    catalog/      # Ingrédients, Recettes, OCR étiquettes (TENANT)
    company/      # UserCompanyRole, context processor (TENANT)
    users/        # User partagé (SHARED)
    tenants/      # Tenant + Domain (SHARED)
    ciqual/       # Base ANSES 3484 entrées (SHARED)
    utilities/    # Allergen, VatRate (SHARED)
    pricing/      # PriceRecord (TENANT) — CODÉ
    purchasing/   # BL/Factures, Fournisseurs, OCR (TENANT) — CODÉ
    butchery/     # Démontage boucherie (TENANT) — CODÉ
    stock/        # (vide)
    production/   # (vide)
    planning/     # (vide)
    sales/        # (vide)
    pms/          # (vide)
    welcome/      # Login, logout, dashboard (TENANT)
  config/
    settings/base.py
    urls.py
  static/
    css/charte.css
    vendors/ (bootstrap, fontawesome, alpinejs, htmx)
    images/logo_sans_fond.png
  templates/
    base/_base.html
    welcome/login.html, dashboard.html
    catalog/ingredient_list.html, ingredient_form.html
             ingredient_detail.html, ingredient_confirm_delete.html
             partials/ingredient_table.html
    purchasing/document_list.html, document_detail.html, document_upload.html
               supplier_list.html, supplier_detail.html, supplier_form.html
               ingredient_create_from_line.html
               partials/document_line_row.html
    butchery/  template_list.html, template_detail.html, template_form.html
               template_line_form.html
               session_list.html, session_detail.html, session_form.html
               session_line_form.html
               yield_list.html, yield_detail.html
               partials/template_lines_tree.html
               partials/session_lines_table.html
               partials/session_line_row.html
  media/
    ingredients/labels/  (photos étiquettes OCR)
```

## Tenant de développement
- schema_name : "test"
- domain : test.localhost
- Accès : http://test.localhost:8000/
- Lancer le serveur : `python manage.py runserver 0.0.0.0:8000`

## Authentification
- LOGIN_URL = "login"
- LOGIN_REDIRECT_URL = "dashboard"
- LOGOUT_REDIRECT_URL = "login"
- 5 rôles : admin, owner, production, worker, cleaning
- UserCompanyRole dans apps/company/models.py (TENANT)
- Context processor : apps/company/context_processors.py
  → injecte current_company, perms_*, pms_alerts_count, stock_alerts_count

## Charte graphique
- Nom : L'Atelier
- Couleurs : #458651 (vert principal), #97b879 (vert clair)
- Fonts : Ubuntu (titres) + Inter (corps)
- Navigation bureau : top navbar avec dropdowns Bootstrap
- Navigation mobile : bottom tab bar (5 icônes) + drawer "Plus"
- Breakpoint mobile : 767px

## Apps SHARED (schema public)
users, tenants, ciqual, utilities

## Apps TENANT (schema par client)
catalog, company, purchasing, stock, production, planning, sales, pms, pricing, welcome, butchery

---

## État des modèles

### apps/catalog/models.py
**IngredientCategory**

**Ingredient** (complet)
- Champs : name, category, allergens, composition, label_photo
- purchase_unit, use_unit, net_weight_kg, net_volume_l
- pieces_per_package, packages_per_purchase_unit
- yield_rate (stocké 0-1, saisi 0-100 via formulaire)
- reference_price (gardé temporairement, sera remplacé par PriceRecord)
- ciqual_ref (FK → CiqualIngredient)
- Valeurs nutri : energy_kj/kcal, fat, saturates, carbs, sugars, protein, salt, fiber
- Flags : is_organic, is_vegan, is_veggie, is_active
- Températures : target_cooking_temp, target_keeping_temp_min/max
- OCR automatique via signal post_save → apps/catalog/services/label_ocr.py

**RecipeCategory**

**Recipe** (complet)
- recipe_type : recipe | sub_recipe | product
- output_quantity, output_unit, output_weight_kg
- is_sellable, selling_price_ttc, vat_rate (FK → VatRate)
- selling_price_ht : property calculée depuis TTC + TVA
- shelf_life_days, shelf_life_after_opening_days
- yield_rate, number_of_servings
- Détection cycle : _get_all_sub_recipe_ids() + clean()
- Calcul coût : get_total_cost() récursif, cost_per_serving, margin, margin_rate

**RecipeLine**
- ingredient XOR sub_recipe (CheckConstraint + clean())
- quantity, unit, note, order
- get_line_cost() : calcul récursif

**RecipeStep**
- order, title, description, duration_minutes, temperature_c
- Contrainte unique (recipe, order)

**RecipeStepPhoto** — step (FK), photo, caption, order

**RecipeEquipment**
- recipe, equipment (FK → company.Equipment), batch_size, batch_unit
- step (FK → RecipeStep, optionnel)
- cycles_needed(total_quantity) : math.ceil

### apps/utilities/models.py
- Allergen (14 allergènes UE chargés via fixture)
- VatRate

### apps/pricing/models.py (CODÉ)
**PriceRecord**
- tenant, ingredient (FK), recipe (FK, optionnel)
- channel : purchase | retail | wholesale | internal
- price_ht, vat_rate, valid_from, valid_until
- source : manual | ocr_bl | butchery | import
- notes

### apps/purchasing/models.py (CODÉ)
**Supplier**
- tenant, name, address, zipcode, city, phone, email
- siret, rcs, vat_number, is_active

**SupplierContact** — supplier, first_name, last_name, job_title, phone, mobile, email

**SupplierIngredient**
- supplier, ingredient, supplier_item_name
- negotiated_price, is_preferred

**DeliveryDocument**
- tenant, supplier (FK, nullable), document_type (bl/invoice/credit/other)
- reference, document_date, status (pending/parsed/validated/error)
- original_file, ocr_raw (JSONField)
- Lien vers supplier_extracted dans ocr_raw si fournisseur non reconnu

**DeliveryLine**
- document, line_type (product/sector_tax/discount/shipping/other)
- raw_label, quantity, unit, unit_price_ht, total_ht, tax_code
- matched_ingredient (FK), match_score, match_confirmed
- applied (bool), reception_line (FK optionnel)

**SupplierLabelMapping** — apprentissage matching fuzzy
- tenant, supplier (FK nullable), raw_label, normalized_label
- ingredient (FK), score (renforce à chaque confirmation), last_seen
- UniqueConstraint: tenant + supplier + normalized_label

**Reception** — tenant, company, supplier, delivery_date, invoice_number

**ReceptionLine** — reception, ingredient, supplier_ref, invoiced_quantity, invoiced_price, invoiced_amount

### apps/butchery/models.py (CODÉ)
**CarcassTemplate** — gabarit réutilisable de démontage
- tenant, name, species (beef/veal/lamb/pork/poultry/other)
- purchase_unit, description, is_active

**CarcassTemplateLine** — structure récursive infinie
- template, parent (FK self nullable), name, norm_code
- output_type (ingredient/sellable/byproduct/waste)
- linked_ingredient (FK), selling_price_ttc, vat_rate
- expected_yield_pct, order, notes

**ButcherySession** — session de découpe réelle
- tenant, template (FK nullable), delivery_line (FK nullable)
- description, species, session_date, butcher (FK User)
- status : open | completed | validated
- purchase_weight_kg, purchase_price_per_kg, purchase_total_ht
- sector_tax_total_ht, processing_cost_ht
- total_cost_ht : property (achat + taxes + prestation)
- Résultats calculés : total_output_weight_kg, total_waste_kg
- real_yield_pct, avg_cost_per_kg, global_margin_rate (en %)

**ButcheryLine** — pièce pesée, structure récursive
- session, parent_line (FK self nullable), template_line (FK nullable)
- name, output_type (ingredient/sellable/byproduct/waste/processing)
- real_weight_kg, linked_ingredient (FK), selling_price_ttc, vat_rate
- cost_per_kg, total_cost, theoretical_ca (calculés à la clôture)
- byproduct_selling_price, byproduct_sold, is_confirmed, order

**YieldRecord** — historique rendements par session
- session (OneToOne), template, supplier, session_date
- purchase_weight_kg, purchase_price_per_kg, total_cost_ht
- global_yield_pct, waste_pct, effective_cost_per_kg, global_margin_rate
- yields_data (JSONField) : détail par pièce

---

## OCR étiquettes
- Service : apps/catalog/services/label_ocr.py
- Moteur 1 : Tesseract 5.3.4 (fra+eng+deu+spa)
- Moteur 2 : Mistral Vision (fallback si confiance < 60%)
- Déclenché : signal post_save sur Ingredient.label_photo
- Extrait : composition, allergènes, valeurs nutri, poids/volume
- Règle : remplit uniquement les champs VIDES

## OCR BL/Factures
- Service : apps/purchasing/services/document_parser.py
- Parsing via Mistral Small LLM (prompt structuré JSON)
- Extrait : produits, taxes filière (CVO/INTERBEV/RSD/TEO), remises, frais port
- Détection fournisseur : cherche en base par name/siret/vat/rcs, sinon extraction LLM
- Matching ingrédients : rapidfuzz token_sort_ratio + apprentissage SupplierLabelMapping
- Auto-confirmation lignes ≥ 85% de score
- Service : apps/purchasing/services/price_applier.py
  → applique les prix vers PriceRecord + crée Reception/ReceptionLine

---

## URLs actives

### Welcome
- `/` → dashboard
- `/login/` → login
- `/logout/` → logout

### Catalog
- `/catalog/ingredients/` → liste
- `/catalog/ingredients/add/` → créer
- `/catalog/ingredients/<pk>/` → détail
- `/catalog/ingredients/<pk>/edit/` → modifier
- `/catalog/ingredients/<pk>/delete/` → supprimer
- `/catalog/ingredients/search/` → HTMX recherche

### Purchasing
- `/purchasing/documents/` → liste documents
- `/purchasing/documents/upload/` → upload BL/facture
- `/purchasing/documents/<pk>/` → détail + matching lignes
- `/purchasing/documents/<pk>/validate/` → valider + appliquer prix
- `/purchasing/documents/<pk>/lines/<lpk>/match/` → correction matching HTMX
- `/purchasing/documents/<pk>/lines/<lpk>/confirm/` → confirmation HTMX
- `/purchasing/documents/<pk>/lines/<lpk>/create-ingredient/` → créer ingrédient depuis ligne
- `/purchasing/documents/<pk>/supplier/add/` → créer fournisseur depuis document
- `/purchasing/suppliers/` → liste fournisseurs
- `/purchasing/suppliers/add/` → créer fournisseur
- `/purchasing/suppliers/<pk>/` → détail fournisseur
- `/purchasing/suppliers/<pk>/edit/` → modifier fournisseur

### Butchery
- `/butchery/templates/` → liste gabarits
- `/butchery/templates/add/` → créer gabarit
- `/butchery/templates/<pk>/` → détail gabarit (arbre pièces)
- `/butchery/templates/<pk>/edit/` → modifier gabarit
- `/butchery/templates/<pk>/lines/add/` → ajouter pièce
- `/butchery/templates/<pk>/lines/<lpk>/edit/` → modifier pièce
- `/butchery/templates/<pk>/lines/<lpk>/delete/` → supprimer pièce
- `/butchery/sessions/` → liste sessions
- `/butchery/sessions/add/` → nouvelle session
- `/butchery/sessions/<pk>/` → détail session (saisie progressive)
- `/butchery/sessions/<pk>/edit/` → modifier session
- `/butchery/sessions/<pk>/close/` → terminer session
- `/butchery/sessions/<pk>/validate/` → calculer prix de revient
- `/butchery/sessions/<pk>/lines/add/` → ajouter pesée (HTMX)
- `/butchery/sessions/<pk>/lines/<lpk>/edit/` → modifier pesée
- `/butchery/sessions/<pk>/lines/<lpk>/delete/` → supprimer pesée (HTMX)
- `/butchery/sessions/<pk>/lines/<lpk>/confirm/` → confirmer pesée (HTMX)
- `/butchery/yields/` → historique rendements
- `/butchery/yields/<pk>/` → détail rendement

---

## Calcul prix de revient boucherie
Méthode coûts joints par prix de vente (joint cost allocation) :
```
PV_HT(pièce)      = PV_TTC(pièce) / (1 + TVA)
CA_total_HT       = Σ PV_HT(pièce) × poids(pièce)
marge_totale_HT   = CA_total_HT - coût_total_HT
taux_marge_global = marge_totale_HT / CA_total_HT  (stocké en %)
Nouveau_PA(pièce) = PV_HT(pièce) × (1 - taux_marge_global/100)
```
Toutes les pièces ont le même taux de marge → prix de revient proportionnel au PV.
coût_total_HT = achat + taxes_filière + prestation_externe

---

## Navbar (dropdowns Bootstrap)
- **Catalogue** → Ingrédients, Recettes
- **Achats** → BL & Factures, Fournisseurs
- **Boucherie** → Sessions, Gabarits, Rendements
- Stock, Production, Planning, PMS, CA (liens directs, vides)

## Bug connu à corriger
- `_base.html` : `{% block nav_butchery %}` en double (lignes ~100 et ~225)
  → supprimer le bloc ligne 225 et son dropdown entourant

---

## Commandes utiles
```bash
python manage.py runserver 0.0.0.0:8000
python manage.py migrate_schemas
python manage.py migrate_schemas --shared
python manage.py makemigrations <app>
python manage.py shell
# Dans le shell :
from django_tenants.utils import schema_context
with schema_context('test'): ...
```

---

## Décisions techniques actées
- Pas de django.contrib.auth.permissions → matrice custom dans UserCompanyRole
- Prix dans PriceRecord séparé (pas dans Recipe/Ingredient)
- yield_rate stocké entre 0 et 1, saisi entre 0 et 100 (conversion dans clean_)
- Alertes PMS/stock calculées à chaque requête (cache Redis plus tard)
- Superuser court-circuite toutes vérifications de rôle
- global_margin_rate stocké en % (ex: 29.62) pas en décimal (0.2962)
- Formulaires Django : champs optionnels avec setdefault() sur request.POST.copy()
  pour éviter les erreurs de validation sur champs non affichés

## Prochaines étapes
1. **Bug navbar** : supprimer le doublon `nav_butchery` dans `_base.html`
2. **CRUD Recettes** : liste, formulaire avec lignes dynamiques HTMX, détail
   - Formulaire recette : lignes ajoutables (ingrédient OU sous-recette)
   - Affichage coût de revient en temps réel (HTMX)
   - Au moins 3 niveaux de sous-recettes
3. **Import CA** : depuis logiciel de caisse (CSV/Excel)
4. **Prévision CA** : régression logistique ou autre méthode (N-1 + tendance)
5. **Lien BL → Session boucherie** : bouton "Démonter" depuis une ligne BL

---

## Pour démarrer une nouvelle conversation
```
Je travaille sur le projet L'Atelier. Lis d'abord le fichier JOURNAL.md 
qui est dans /mnt/project/ pour te mettre dans le contexte.
```
