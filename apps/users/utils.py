"""
Utilitaires pour la gestion des comptes utilisateurs.
"""
import re
import unicodedata


def generate_username(first_name: str, last_name: str) -> str:
    """
    Génère un username unique au format p.nom
    En cas de collision : p.nom.2, p.nom.3, etc.

    Exemples :
        Georges Dupont  → g.dupont
        Guillaume Dupont (si g.dupont existe) → g.dupont.2
        De La Fère Olivier → o.de-la-fere → o.delafere
    """
    from apps.users.models import User

    def normalize(s: str) -> str:
        """Supprime accents, espaces, caractères spéciaux."""
        s = s.lower().strip()
        s = unicodedata.normalize('NFD', s)
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        s = re.sub(r'[^a-z0-9]', '', s)
        return s

    first = normalize(first_name)
    last  = normalize(last_name)

    if not first or not last:
        raise ValueError("Prénom et nom sont requis pour générer un username.")

    base = f"{first[0]}.{last}"

    if not User.objects.filter(username=base).exists():
        return base

    i = 2
    while User.objects.filter(username=f"{base}.{i}").exists():
        i += 1
    return f"{base}.{i}"