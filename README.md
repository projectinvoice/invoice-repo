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

# Système d'abonnement — Guide de mise en route

## Ce qui a été ajouté

1. **Modèles** (`InvoiceApp/models.py`)
   - `Subscription` : 1 par entreprise, plan (`monthly`/`annual`), `trial_end_date` (7 jours après
     l'inscription), `active_until` (mis à jour à chaque paiement réussi). Statut calculé automatiquement :
     `trial` → `promo` → `active` → `expired`.
   - `SubscriptionPayment` : historique des transactions MoneyFusion (en attente / réussi / échoué).
   - `PromoCode` / `PromoCodeRedemption` : codes promo à durée définie (voir plus bas).

2. **Inscription** (`register_company` + `register.html`) : une étape "Choisissez votre plan" (+ champ
   code promo optionnel) a été ajoutée à l'assistant d'inscription. À la création du compte, un
   `Subscription` est créé avec 7 jours d'essai gratuit, quel que soit le plan choisi.

3. **Blocage automatique** (`InvoiceApp/middleware.py`) : dès que l'essai (ou un code promo, ou un
   paiement) expire sans rien d'actif, toute page autre que le **dashboard** (et la page **Abonnement**)
   redirige automatiquement vers le dashboard (ou renvoie une erreur 402 pour les requêtes POST/API).
   Ceci protège aussi côté serveur, pas seulement visuellement.

4. **Interface grisée** (`dashboard.html`) : quand l'abonnement est expiré, tous les liens du menu, les
   cartes de statistiques et les boutons d'action sont grisés (`opacity` + `pointer-events: none`) sauf
   le dashboard lui-même, la déconnexion et le bouton "S'abonner maintenant". Une bannière s'affiche en
   haut du dashboard pendant l'essai / la période promo (compte à rebours) et après expiration.

5. **Paiement MoneyFusion** (`subscription_page`, `initiate_subscription_payment`, `moneyfusion_webhook`,
   `moneyfusion_return`) : intégration par redirection. L'entreprise clique sur "Payer avec MoneyFusion"
   → une transaction est créée → redirection vers le guichet MoneyFusion → à la fin du paiement,
   MoneyFusion appelle votre `webhook_url` (webhook serveur-à-serveur, propre à chaque transaction) ET
   redirige le client vers `return_url` avec `?token=...`. Dans les deux cas, le statut réel est
   revérifié auprès de l'API MoneyFusion (jamais fait confiance aux données envoyées directement par
   le navigateur).

## ⚠️ Point à vérifier avant la mise en production : l'URL de vérification du statut

L'intégration MoneyFusion repose sur 3 appels :
1. **Initialisation** du paiement → POST vers votre URL d'API MoneyFusion (confirmé, documenté).
2. **Retour du client** sur votre site avec `?token=...` (confirmé, documenté).
3. **Vérification du statut** d'un paiement via ce token, pour confirmer le paiement sans jamais faire
   confiance aveuglément au webhook ou au retour navigateur.

Pour le point 3, la documentation publique de MoneyFusion (`docs.moneyfusion.net`) bloque l'accès
automatisé (robots.txt), donc je n'ai pas pu confirmer par une requête réelle l'URL exacte de
vérification de statut. Le code utilise actuellement ce format, déduit de l'écosystème FusionPay
(bibliothèques JS/PHP officielles et communautaires) :

```
https://www.pay.moneyfusion.net/paiementNotif/{token}
```

**Avant de mettre en production**, merci de confirmer cette URL en consultant :
- https://docs.moneyfusion.net/fr/ (section vérification de paiement / `checkPaymentStatus`)
- ou en contactant le support MoneyFusion, ou en inspectant le comportement de la méthode
  `checkPaymentStatus()` d'une des bibliothèques officielles (JS : `npm install fusionpay`, PHP :
  `composer require assemien-dev/money-fusion-php`).

Si l'URL réelle diffère, il n'y a **qu'un seul endroit à changer** :

```bash
export MONEYFUSION_STATUS_CHECK_TEMPLATE="https://url-correcte.com/verif/{token}"
```

(`{token}` sera remplacé automatiquement par le `tokenPay` de la transaction — gardez ce
placeholder tel quel dans la valeur que vous définissez.)

## Configuration à faire avant la mise en production

Dans `InvoiceProject/settings.py`, ces variables d'environnement sont attendues :

```bash
export MONEYFUSION_API_URL="https://www.pay.moneyfusion.net/VOTRE-MARCHAND/VOTRE-CLE/pay/"
export MONEYFUSION_STATUS_CHECK_TEMPLATE="https://www.pay.moneyfusion.net/paiementNotif/{token}"  # à confirmer, voir ci-dessus
export SITE_BASE_URL="https://votre-domaine.com"   # doit être accessible publiquement (pas localhost)
```

`MONEYFUSION_API_URL` est **propre à votre compte** : connectez-vous sur votre tableau de bord
MoneyFusion (moneyfusion.net), créez une "application" de paiement, et copiez l'URL d'API unique
qui vous est fournie.

⚠️ `webhook_url` doit être **joignable depuis Internet** — MoneyFusion ne peut pas appeler
`http://127.0.0.1:8000`. En développement local, utilisez un tunnel (ngrok, cloudflared) pour tester
le webhook, ou testez uniquement le flux "return" (vérification faite aussi côté `moneyfusion_return`).

## Étapes pour déployer ces changements

```bash
pip install -r requirements.txt   # ajoute `requests`, utilisé pour appeler l'API MoneyFusion
python manage.py migrate          # applique les migrations 0002 à 0004
```

Les migrations ont été écrites manuellement (Django n'était pas installé dans cet environnement
d'édition) — elles n'ont donc **pas pu être testées par exécution**. Avant la mise en production,
lancez `python manage.py makemigrations --check` puis `python manage.py migrate` sur votre
environnement de développement pour confirmer qu'elles s'appliquent sans erreur.

## Codes promo (offrir de l'accès sans paiement)

Pour donner un mois gratuit à vos premiers utilisateurs :

1. Connectez-vous avec un compte **staff** (`is_staff=True`, réglable depuis `/admin/` ou en base).
2. Allez sur **Codes promo** dans le menu du dashboard (visible uniquement pour le staff), ou
   directement sur `/admin-tools/promo-codes/`.
3. Renseignez la durée en jours (ex: `30`), une note facultative (ex: "Lancement bêta"), et
   éventuellement une limite d'utilisations ou une date limite. Laissez le champ "Code personnalisé"
   vide pour un code aléatoire, ou choisissez le vôtre (ex: `LANCEMENT30`).
4. Cliquez sur **Générer le code** puis partagez-le aux entreprises concernées.

Les entreprises peuvent l'utiliser de deux façons :
- **À l'inscription** : un champ "Code promo" optionnel a été ajouté à l'assistant d'inscription.
- **Depuis un compte existant** : sur la page `/subscription/`, un champ "Vous avez un code promo ?"
  permet de l'appliquer à tout moment (utile si l'essai de 7 jours est déjà expiré).

Chaque code ne peut être utilisé qu'**une seule fois par entreprise**. Si un avantage (essai, autre
code promo, ou abonnement payé) est encore actif au moment de l'utilisation, la durée du code s'ajoute
à la suite de celui-ci plutôt que de le remplacer.

Vous pouvez aussi gérer les codes depuis l'admin Django classique (`/admin/InvoiceApp/promocode/`),
qui offre les mêmes informations (utilisations, statut, historique par entreprise).

## Configuration (.env)

Un fichier `.env.example` est fourni à la racine du projet, avec toutes les variables utilisées
(MoneyFusion, email, `SITE_BASE_URL`, etc.) et leur description. Pour démarrer :

```bash
cp .env.example .env
```

Puis remplissez les valeurs réelles dans `.env`. Ce fichier est chargé automatiquement au démarrage de
Django (via `python-dotenv`, maintenant dans `requirements.txt`) et **n'est jamais versionné** (déjà
exclu par `.gitignore`) — chaque environnement (dev, serveur de prod) a le sien avec ses propres
valeurs.

⚠️ Un fichier `.env` avec des valeurs par défaut (sans secret réel) est aussi inclus dans cette archive
pour que le projet fonctionne immédiatement en développement local — pensez à le remplacer par vos
vraies valeurs avant la mise en production.

## Notes importantes

- Les entreprises déjà existantes en base (créées avant cette mise à jour) n'ont pas de `Subscription`.
  Le code gère ce cas sans planter (accès normal, pas de blocage) mais il est recommandé de créer un
  script pour leur attribuer un abonnement (essai ou actif) après le déploiement.
- Le prix mensuel (6 000 FCFA) et annuel (50 000 FCFA) sont définis dans `SUBSCRIPTION_PLAN_PRICES`
  (`InvoiceApp/models.py`). Modifiables à un seul endroit.
- Le vendeur (accès via code entreprise + PIN, `/vendeur/...`) est également bloqué automatiquement si
  l'abonnement de son entreprise est expiré (seul `/vendeur/` — le tableau de bord vendeur — reste
  accessible).
- Chaque `SubscriptionPayment` garde deux identifiants : `transaction_id` (généré par notre application,
  pour notre suivi interne) et `provider_token` (le `tokenPay` renvoyé par MoneyFusion, utilisé pour la
  vérification de statut et le rapprochement webhook).

## Récupération de mot de passe par email

Une entreprise qui a oublié son mot de passe peut le réinitialiser depuis la page de connexion :

1. **Connexion → "Mot de passe oublié ?"** (`/mot-de-passe-oublie/`) : elle saisit son email.
2. Si un compte existe avec cet email, un lien à usage unique est envoyé (valable 24h par défaut,
   réglable via `PASSWORD_RESET_TIMEOUT`). La réponse affichée est **toujours la même**, que l'email
   existe ou non, pour ne pas permettre à quelqu'un de deviner quels emails sont enregistrés.
3. Le lien mène vers `/reinitialiser-mot-de-passe/<uid>/<token>/`, qui vérifie que le lien est valide
   et n'a pas déjà été utilisé, avant de permettre de choisir un nouveau mot de passe (8 caractères
   minimum).

La sécurité du token repose sur `django.contrib.auth.tokens.default_token_generator`, le même
mécanisme standard et éprouvé utilisé par Django lui-même — le lien devient automatiquement invalide
dès que le mot de passe est changé ou que le délai expire.

### Configuration email à faire avant la mise en production

Par défaut, les emails s'affichent seulement dans la console du serveur (pratique pour tester en
développement, mais **aucun email n'est réellement envoyé**). Pour un envoi réel, configurez un
serveur SMTP via variables d'environnement, par exemple avec Gmail :

```bash
export EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
export EMAIL_HOST="smtp.gmail.com"
export EMAIL_PORT="587"
export EMAIL_USE_TLS="True"
export EMAIL_HOST_USER="votre-adresse@gmail.com"
export EMAIL_HOST_PASSWORD="votre-mot-de-passe-application"   # pas votre mot de passe Gmail normal
export DEFAULT_FROM_EMAIL="no-reply@votre-domaine.com"
```

Pour Gmail, il faut générer un **mot de passe d'application** (pas votre mot de passe habituel) depuis
les paramètres de sécurité du compte Google. En production, un service dédié (SendGrid, Mailgun,
Brevo, Amazon SES...) est recommandé plutôt qu'une boîte Gmail classique, pour la délivrabilité.
