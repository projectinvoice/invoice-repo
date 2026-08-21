# Découpage de `views.py` en package

## Ce qui a changé

`InvoiceApp/views.py` (2261 lignes, 87 fonctions) est devenu `InvoiceApp/views/`
(un package de 14 fichiers, ~150-280 lignes chacun) :

| Fichier | Contenu |
|---|---|
| `_common.py` | Tous les imports partagés (Django, reportlab, modèles...) — chaque autre fichier fait `from ._common import *` pour retrouver exactement le même environnement qu'avant |
| `ai_assistant.py` | Assistant IA (fonctions outils Gemini + endpoint de chat) |
| `auth.py` | Inscription, connexion, activation, mot de passe |
| `subscription.py` | Abonnement, paiement MoneyFusion, codes promo |
| `dashboard.py` | Tableau de bord + API du graphique de CA |
| `company.py` | Paramètres de l'entreprise |
| `agents.py` | Agents, rôles d'agent, engins |
| `products.py` | Produits |
| `clients.py` | Clients |
| `suppliers.py` | Fournisseurs + approvisionnements |
| `payments.py` | Types et modes de paiement |
| `sales.py` | Ventes |
| `invoices.py` | Factures, paiements de facture, PDF |
| `vendor.py` | Espace vendeur (agents), auth séparée |
| `stock.py` | Chargements/retours de stock |
| `__init__.py` | Ré-exporte tout, pour compatibilité totale avec l'existant |

## Pourquoi c'est sûr (zéro changement de comportement)

- **Le code des fonctions n'a pas été retapé à la main.** Je l'ai extrait par analyse
  syntaxique (`ast`) directement depuis l'original, ligne par ligne, décorateurs
  compris — donc caractère pour caractère identique à avant.
- **`urls.py` n'a pas bougé.** Il fait `from InvoiceApp import views as invoice_views`
  puis `invoice_views.dashboard`, `invoice_views.add_sale`, etc. — ça continue de
  fonctionner à l'identique car `__init__.py` ré-exporte explicitement les 87
  fonctions et 6 constantes d'origine, avec les mêmes noms.
- **Vérifications faites avant livraison :**
  - Chaque nom de fonction/constante retrouvé exactement une fois (aucune perte, aucun doublon) — comparé par script contre l'original.
  - Tous les fichiers `.py` du projet re-validés syntaxiquement (`ast.parse`).
  - Scan automatique de chaque nouveau fichier à la recherche de noms utilisés
    mais jamais importés/définis (variable manquante) — aucun trouvé.
  - Recherche de toute autre partie du projet (`admin.py`, `templatetags/`,
    tests) qui référencerait `views.py` directement — seuls `urls.py` et les
    tests le font, et les deux continuent de fonctionner sans changement
    (à une exception près, corrigée : `tests_multi_tenant_isolation.py` mockait
    `InvoiceApp.views.http_requests.post` ; ça pointe maintenant vers
    `InvoiceApp.views.ai_assistant.http_requests.post`, l'endroit réel où le code
    vit désormais).

## Limite honnête

Comme pour les tests d'isolation, je n'ai pas pu lancer `python manage.py runserver`
ni `python manage.py test` dans cet environnement (pas d'accès réseau pour
installer Django). J'ai fait une revue statique aussi rigoureuse que possible
(voir ci-dessus), mais **relance bien les tests avant de considérer ce
découpage comme définitif** :

```bash
python manage.py test
python manage.py runserver   # puis navigue sur quelques pages pour confirmer
```

Si quoi que ce soit casse, dis-le-moi — je corrige immédiatement.

## Pour ajouter une nouvelle vue demain

1. Choisis le fichier du bon domaine (ex. une nouvelle route sur les ventes → `sales.py`).
2. Écris la fonction normalement (tout ce qui était disponible avant l'est toujours, via `_common.py`).
3. Ajoute-la à la liste d'import correspondante dans `__init__.py`.
4. Ajoute la route dans `InvoiceProject/urls.py` comme avant — rien d'autre ne change.
