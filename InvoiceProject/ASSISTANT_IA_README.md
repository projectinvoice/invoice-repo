# Assistant IA flottant — ce qui a été ajouté

## 1. Fichiers modifiés / créés

| Fichier | Rôle |
|---|---|
| `InvoiceProject/settings.py` | Ajout de `GEMINI_API_KEY` et `GEMINI_MODEL` (lus depuis `.env`) |
| `.env` / `.env.example` | Nouvelle variable `GEMINI_API_KEY` (vide, à remplir) et `GEMINI_MODEL=gemini-2.5-flash` |
| `InvoiceProject/urls.py` | Deux routes : `api/ai-chat/` et `api/ai-chat/init/` |
| `InvoiceApp/views.py` | Fonctions "outils" (`get_ventes`, `get_etat_financier`, `get_produits_stock`, `get_clients`, `get_factures`) + la vue `ai_chat_api` qui pilote Gemini avec function calling, + `ai_chat_init` |
| `InvoiceApp/static/InvoiceApp/js/ai_assistant.js` | Le widget flottant (bouton + panneau de chat), auto-injecté |
| 23 templates (`dashboard.html`, `sale_list.html`, `invoice_list.html`, `product_list.html`, `edit_product.html`, `client_list.html`, `edit_client.html`, `supplier_list.html`, `edit_supplier.html`, `supply_list.html`, `stock.html`, `stock_loads.html`, `agent_list.html`, `add_agent.html`, `edit_agent.html`, `agent_roles_manage.html`, `payment_type_list.html`, `payment_method_list.html`, `company_settings.html`, `change_password.html`, `engine_list.html`, `subscription.html`) | `{% load static %}` + `<script src="{% static 'InvoiceApp/js/ai_assistant.js' %}"></script>` avant `</body>` |

Aucune dépendance Python supplémentaire : `requests` était déjà dans `requirements.txt` et sert à appeler l'API Gemini en REST (pas de SDK Google à installer). Aucune migration nécessaire (aucun modèle modifié).

## 2. Mise en service

1. Récupère une clé API sur https://aistudio.google.com/app/apikey
2. Dans `.env`, renseigne :
   ```
   GEMINI_API_KEY=ta_clé_ici
   GEMINI_MODEL=gemini-2.5-flash
   ```
3. Redémarre le serveur (`python manage.py runserver`). Rien d'autre à faire : le widget est déjà branché sur toutes les pages listées ci-dessus.

Si la clé n'est pas renseignée, le widget reste visible mais répond poliment qu'il n'est pas encore configuré (pas de crash).

## 3. Comment ça marche

- Le bouton flottant (violet, en bas à droite) ouvre un panneau de chat positionné à droite de l'écran, sur toutes les pages où il a été inclus — **sans jamais changer de page**.
- La conversation (historique brut envoyé à Gemini + bulles affichées) est stockée dans `sessionStorage` du navigateur : elle **reste dans le contexte** même si l'utilisateur navigue entre les pages de l'app (tant que l'onglet reste ouvert). Un bouton "Effacer" permet de repartir de zéro.
- Côté serveur, `ai_chat_api` reçoit le message + l'historique, appelle Gemini avec 5 fonctions déclarées (ventes, état financier, stock, clients, factures). Quand Gemini demande à appeler une fonction, le serveur exécute la requête Django réelle **filtrée sur l'entreprise connectée** (`company=request.user`), renvoie le résultat à Gemini, qui peut enchaîner plusieurs appels avant de formuler sa réponse finale (jusqu'à 6 aller-retours). Gemini est instruit de toujours proposer des recommandations concrètes après une analyse.
- Toutes les données restent cloisonnées par entreprise : chaque fonction filtre systématiquement par `company=request.user`, aucune fuite entre comptes.

## 4. Portée volontairement limitée

Le widget n'est **pas** ajouté sur : `landing.html`, `login.html`, `register.html`, `forgot_password.html`, `reset_password_confirm.html`, `activation_invalid.html`, `vendor_login.html`, `seller.html`, `vendor_dashboard.html`, `delete_account.html`, `subscription_return.html`, `promo_codes_admin.html`.

Raison : les pages "vendeur" (`seller.html`, `vendor_dashboard.html`) utilisent un système d'authentification par session distinct (`request.agent`, pas `request.user`) — l'endpoint IA est protégé par `@login_required` sur le compte entreprise, donc il ne fonctionnerait pas pour un agent connecté. Si tu veux l'assistant aussi côté vendeurs, il faudra une variante de l'endpoint adaptée à `request.agent` (dites-le-moi, je peux l'ajouter).

## 5. Pour aller plus loin (pas fait, sur demande)

- Ajouter l'IA aux pages vendeurs (`request.agent`)
- Historique de conversation persistant en base (actuellement en `sessionStorage`, donc perdu à la fermeture de l'onglet)
- Fonctions supplémentaires (ex. `get_supplies`, `get_agents_performance`)
