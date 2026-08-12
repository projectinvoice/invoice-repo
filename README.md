# ⭕⭕🛑invoice-repo 🛑⛔📛
print("bonjour à tous")


⭕⭕🛑nouvelle mise a jour🛑⛔📛 :
desormais si tu fait une modification qui t'amene a installer de nouvelles librairies,

tu doit taper la commande pip freeze > requirements.txt

cette commandes te permet de recuperer la liste des librairies requises pour le bon fonctionnement du site.

ce n'est qu'apres cette commande que tu doit envoyer ta modification sur github.


la personne qui es censée recevoir le code

tapera la commande pip install -r requirements.txt pour metre a jour ces librairies avant de demarer le serveur.

attention avant chacune de ces comandes , il faut s'assurer que l'environnement virtuel est activé

==========================================================================================================================================================================================================================


==========================================================================================================================================================================================================================

# Système d'abonnement — Guide de mise en route

## Ce qui a été ajouté

1. **Modèles** (`InvoiceApp/models.py`)
   - `Subscription` : 1 par entreprise, plan (`monthly`/`annual`), `trial_end_date` (7 jours après
     l'inscription), `active_until` (mis à jour à chaque paiement réussi). Statut calculé automatiquement :
     `trial` → `active` → `expired`.
   - `SubscriptionPayment` : historique des transactions CinetPay (en attente / réussi / échoué).

2. **Inscription** (`register_company` + `register.html`) : une étape "Choisissez votre plan" a été
   ajoutée à l'assistant d'inscription. À la création du compte, un `Subscription` est créé avec 7 jours
   d'essai gratuit, quel que soit le plan choisi.

3. **Blocage automatique** (`InvoiceApp/middleware.py`) : dès que l'essai expire sans paiement actif,
   toute page autre que le **dashboard** (et la page **Abonnement**) redirige automatiquement vers le
   dashboard (ou renvoie une erreur 402 pour les requêtes POST/API). Ceci protège aussi côté serveur,
   pas seulement visuellement.

4. **Interface grisée** (`dashboard.html`) : quand l'abonnement est expiré, tous les liens du menu, les
   cartes de statistiques et les boutons d'action sont grisés (`opacity` + `pointer-events: none`) sauf
   le dashboard lui-même, la déconnexion et le bouton "S'abonner maintenant". Une bannière s'affiche en
   haut du dashboard pendant l'essai (compte à rebours) et après expiration.

5. **Paiement CinetPay** (`subscription_page`, `initiate_subscription_payment`, `cinetpay_notify`,
   `cinetpay_return`) : intégration par redirection (recommandée par CinetPay). L'entreprise clique sur
   "Payer avec CinetPay" → une transaction est créée → redirection vers le guichet CinetPay → à la fin
   du paiement, CinetPay appelle votre `notify_url` (webhook serveur-à-serveur) ET redirige le client
   vers `return_url`. Dans les deux cas, le statut réel est revérifié auprès de l'API CinetPay
   (jamais fait confiance aux données envoyées directement par le navigateur).

## Configuration à faire avant la mise en production

Dans `InvoiceProject/settings.py`, deux variables d'environnement sont attendues :

```bash
export CINETPAY_API_KEY="votre_api_key"
export CINETPAY_SITE_ID="votre_site_id"
export SITE_BASE_URL="https://votre-domaine.com"   # doit être accessible publiquement (pas localhost)
```

Récupérez `CINETPAY_API_KEY` et `CINETPAY_SITE_ID` depuis votre compte marchand CinetPay
(menu **Intégrations** sur https://app-new.cinetpay.com).

⚠️ `notify_url` (le webhook) doit être **joignable depuis Internet** — CinetPay ne peut pas appeler
`http://127.0.0.1:8000`. En développement local, utilisez un tunnel (ngrok, cloudflared) pour tester
le webhook, ou testez uniquement le flux "return" (vérification faite aussi côté `cinetpay_return`).

## Étapes pour déployer ces changements

```bash
pip install -r requirements.txt   # ajoute `requests`, utilisé pour appeler l'API CinetPay
python manage.py migrate          # applique la migration 0002 (Subscription, SubscriptionPayment)
```

Une migration a été écrite manuellement (`InvoiceApp/migrations/0002_subscription_subscriptionpayment.py`)
car Django n'était pas installé dans cet environnement d'édition — elle n'a donc **pas pu être testée
par exécution**. Avant la mise en production, lancez `python manage.py makemigrations --check` puis
`python manage.py migrate` sur votre environnement de développement pour confirmer qu'elle s'applique
sans erreur.

## Notes importantes

- Les entreprises déjà existantes en base (créées avant cette mise à jour) n'ont pas de `Subscription`.
  Le code gère ce cas sans planter (accès normal, pas de blocage) mais il est recommandé de créer un
  script pour leur attribuer un abonnement (essai ou actif) après le déploiement.
- Le prix mensuel (6 000 FCFA) et annuel (50 000 FCFA) sont définis dans `SUBSCRIPTION_PLAN_PRICES`
  (`InvoiceApp/models.py`). Modifiables à un seul endroit.
- Le montant envoyé à CinetPay doit être un **multiple de 5** — c'est déjà le cas ici (6000 et 50000).
- Le vendeur (accès via code entreprise + PIN, `/vendeur/...`) est également bloqué automatiquement si
  l'abonnement de son entreprise est expiré (seul `/vendeur/` — le tableau de bord vendeur — reste
  accessible).
