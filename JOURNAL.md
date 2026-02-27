# L'Atelier — Journal de développement

## Stack technique
- Python 3.12, Django 5.2, django-tenants
- PostgreSQL (schemas séparés par tenant)
- HTMX + Alpine.js + Bootstrap 5 + FontAwesome 7
- Tesseract OCR + Mistral Vision (fallback)
- Whitenoise (static files)

## Structure projet
kitchen_optimizer_v2/
apps/
catalog/      # Ingrédients, Recettes, OCR étiquettes
company/      # UserCompanyRole, context processor
users/        # User partagé (SHARED)
tenants/      # Tenant + Domain (SHARED)
ciqual/       # Base ANSES 3484 entrées (SHARED)
utilities/    # Allergen, VatRate (SHARED)
pricing/      # PriceRecord (EN COURS)
purchasing/   # (vide)
stock/        # (vide)
production/   # (vide)
planning/     # (vide)
sales/        # (vide)
pms/          # (vide)
welcome/      # Login, logout, dashboard
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
media/
ingredients/labels/  (photos étiquettes OCR)
Tenant de développement

schema_name : "test"
domain : test.localhost
Accès : http://test.localhost:8000/
Lancer le serveur : python manage.py runserver 0.0.0.0:8000

Authentification

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
5 rôles : admin, owner, production, worker, cleaning
UserCompanyRole dans apps/company/models.py (TENANT)
Context processor : apps/company/context_processors.py
→ injecte current_company, perms_*, pms_alerts_count, stock_alerts_count

Charte graphique

Nom : L'Atelier
Couleurs : #458651 (vert principal), #97b879 (vert clair)
Fonts : Ubuntu (titres) + Inter (corps)
Navigation bureau : top navbar (liens horizontaux, classe .atelier-nav-link)
Navigation mobile : bottom tab bar (5 icônes) + drawer "Plus"
Breakpoint mobile : 767px

Apps SHARED (schema public)

users, tenants, ciqual, utilities

Apps TENANT (schema par client)

catalog, company, purchasing, stock, production, planning, sales, pms, pricing, welcome

État des modèles
apps/catalog/models.py

IngredientCategory
Ingredient (complet)

Champs : name, category, allergens, composition, label_photo
purchase_unit, use_unit, net_weight_kg, net_volume_l
pieces_per_package, packages_per_purchase_unit
yield_rate (stocké 0-1, saisi 0-100 via formulaire)
reference_price (gardé temporairement, sera remplacé par PriceRecord)
ciqual_ref (FK → CiqualIngredient)
Valeurs nutri : energy_kj/kcal, fat, saturates, carbs, sugars, protein, salt, fiber
Flags : is_organic, is_vegan, is_veggie, is_active
Températures : target_cooking_temp, target_keeping_temp_min/max
OCR automatique via signal post_save → apps/catalog/services/label_ocr.py


RecipeCategory
Recipe (complet)

recipe_type : recipe | sub_recipe | product
output_quantity, output_unit, output_weight_kg
is_sellable, selling_price_ttc, vat_rate (FK → VatRate)
selling_price_ht : property calculée depuis TTC + TVA
shelf_life_days, shelf_life_after_opening_days
yield_rate, number_of_servings
Détection cycle : _get_all_sub_recipe_ids() + clean()
Calcul coût : get_total_cost() récursif, cost_per_serving, margin, margin_rate


RecipeLine

ingredient XOR sub_recipe (CheckConstraint + clean())
quantity, unit, note, order
get_line_cost() : calcul récursif


RecipeStep

order, title, description, duration_minutes, temperature_c
Contrainte unique (recipe, order)


RecipeStepPhoto

step (FK), photo, caption, order


RecipeEquipment

recipe, equipment (FK → company.Equipment), batch_size, batch_unit
step (FK → RecipeStep, optionnel)
cycles_needed(total_quantity) : math.ceil



apps/utilities/models.py

Allergen (14 allergènes UE chargés via fixture)
VatRate

apps/pricing/ (EN COURS — pas encore codé)

PriceRecord prévu :

GenericForeignKey → Recipe OU Ingredient
tenant, channel (retail/wholesale/internal)
price_ht, vat_rate, valid_from, valid_until, notes
Remplacera reference_price sur Ingredient
Remplacera selling_price_ttc/ht sur Recipe



OCR étiquettes

Service : apps/catalog/services/label_ocr.py
Moteur 1 : Tesseract 5.3.4 (fra+eng+deu+spa)
Moteur 2 : Mistral Vision (fallback si confiance < 60%)
Déclenché : signal post_save sur Ingredient.label_photo
Extrait : composition, allergènes, valeurs nutri, poids/volume
Règle : remplit uniquement les champs VIDES (pas de conflit CIQUAL/manuel)
Résultat affiché : message flash après save

URLs actives

/                    → dashboard (welcome)
/login/              → login
/logout/             → logout
/catalog/ingredients/         → liste
/catalog/ingredients/add/     → créer
/catalog/ingredients/<pk>/    → détail
/catalog/ingredients/<pk>/edit/   → modifier
/catalog/ingredients/<pk>/delete/ → supprimer
/catalog/ingredients/search/  → HTMX recherche

Prochaine étape

Coder apps/pricing/models.py (PriceRecord)
Puis CRUD Recettes (liste, formulaire avec lignes dynamiques HTMX, détail)
Formulaire recette : lignes ajoutables dynamiquement (ingrédient OU sous-recette)
Affichage coût de revient en temps réel (HTMX)

Commandes utiles
bashpython manage.py runserver 0.0.0.0:8000
python manage.py migrate_schemas
python manage.py migrate_schemas --shared
python manage.py makemigrations <app>
python manage.py shell
# Dans le shell :
from django_tenants.utils import schema_context
with schema_context('test'): ...
Décisions techniques actées

Pas de django.contrib.auth.permissions → matrice custom dans UserCompanyRole
Prix dans PriceRecord séparé (pas dans Recipe/Ingredient)
Démontage carcasses → module apps/butchery séparé (V2.1)
yield_rate stocké entre 0 et 1, saisi entre 0 et 100 (conversion dans clean_)
Alertes PMS/stock calculées à chaque requête (cache Redis plus tard)
Superuser court-circuite toutes vérifications de rôle


Colle ça dans `JOURNAL.md`, sauvegarde, et ouvre une nouvelle conversation en commençant par :

. je te donne les fichiers dans l