# 📦 Configuration du Stockage Médias Cloudflare R2 & Déploiement Render

Ce guide détaille la mise en place pas-à-pas de **Cloudflare R2** pour le stockage persistant des fichiers médias (logos d'entreprises, photos de produits) de votre application **Smart Invoice**, déployée sur **Render**.

---

## 🎯 Pourquoi Cloudflare R2 avec Render ?

Sur Render, le disque d'un Web Service standard est **éphémère** : à chaque nouveau déploiement ou redémarrage de l'instance, tous les fichiers enregistrés localement dans le dossier `media/` sont effacés.

**Cloudflare R2** résout ce problème de manière définitive :
- **Stockage d'objets persistant et illimité** compatible avec l'API Amazon S3.
- **Zéro frais de bande passante sortante (0 $ Egress fees)** : contrairement à AWS S3, l'affichage public des images ne génère aucun coût de transfert.
- **Tier gratuit très généreux** : 10 Go de stockage par mois, 1 million d'opérations d'écriture (Class A) et 10 millions d'opérations de lecture (Class B) offerts chaque mois.
- **Intégration transparente avec Django** : via `django-storages` et `boto3`.

> 💡 **En local (développement & tests) :** Si les variables d'environnement R2 ne sont pas définies, l'application bascule automatiquement sur le stockage local `FileSystemStorage` dans le dossier `media/`.

---

## 🔑 1. Variables d'Environnement Nécessaires

| Variable | Description | Exemple / Format | Obligatoire sur Render |
|---|---|---|---|
| `CLOUDFLARE_R2_BUCKET_NAME` | Nom exact de votre bucket R2 | `smart-invoice-media` | **Oui** |
| `CLOUDFLARE_R2_ACCOUNT_ID` | Identifiant unique de votre compte Cloudflare | `c03289ab712f...` (32 caractères) | **Oui** |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | Clé d'accès de votre jeton API R2 | `3c8f...` (32 caractères) | **Oui** |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | Clé secrète de votre jeton API R2 | `8e2a...` (64 caractères hex) | **Oui** |
| `CLOUDFLARE_R2_CUSTOM_DOMAIN` | Domaine public pour accéder aux images (R2.dev ou domaine personnalisé) | `pub-xxxxxxxxxxxx.r2.dev` ou `media.votredomaine.com` | **Recommandé** |
| `CLOUDFLARE_R2_ENDPOINT_URL` | Endpoint S3 complet (construit automatiquement si omis) | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` | Optionnel |

---

## ☁️ 2. Récupérer les Valeurs dans le Tableau de Bord Cloudflare

Connectez-vous sur votre compte [Cloudflare](https://dash.cloudflare.com/).

### Étape 2.1 — Créer le Bucket R2
1. Dans le menu de gauche, cliquez sur **R2** (ou **Stockage d'objets / R2**).
2. Si c'est votre première utilisation, activez le service R2.
3. Cliquez sur le bouton bleu **Create bucket** (Créer un bucket).
4. Nommez votre bucket (par exemple : `smart-invoice-media`).
5. Conservez l'emplacement par défaut (**Automatic**) ou choisissez votre région de prédilection.
6. Cliquez sur **Create bucket**.
   > 👉 Vous obtenez votre valeur pour : `CLOUDFLARE_R2_BUCKET_NAME=smart-invoice-media`.

### Étape 2.2 — Récupérer l'Account ID (Identifiant de compte)
1. Retournez sur la page principale **R2** (ou ouvrez les détails de votre bucket).
2. Dans le panneau de droite sous **Account details** (Détails du compte), copiez l'**Account ID**.
   > 👉 Vous obtenez votre valeur pour : `CLOUDFLARE_R2_ACCOUNT_ID=votre_account_id_ici`.
   > *(L'URL de l'endpoint S3 sera automatiquement : `https://<votre_account_id>.r2.cloudflarestorage.com`)*.

### Étape 2.3 — Activer l'accès public pour l'affichage des images
Par défaut, les buckets R2 sont privés. Pour que vos utilisateurs et le navigateur puissent afficher les logos et photos produits :
1. Dans votre bucket R2, allez dans l'onglet **Settings** (Paramètres).
2. Descendez jusqu'à la section **Public access** (Accès public).
3. **Option A (Plus rapide, prêt en 1 seconde) : Sous-domaine R2.dev**
   - Cliquez sur **Allow** (Autoriser) en face de *R2.dev subdomain*.
   - Tapez `allow` pour confirmer.
   - Cloudflare vous donne une URL publique au format : `https://pub-xxxxxxxxxxxxxxxxxxxx.r2.dev`.
   - Copiez uniquement le nom de domaine (sans `https://`), par exemple : `pub-xxxxxxxxxxxxxxxxxxxx.r2.dev`.
4. **Option B (Domaine personnalisé de votre marque) :**
   - Si vous possédez votre domaine sur Cloudflare (ex: `votredomaine.com`), cliquez sur **Connect Domain**.
   - Entrez par exemple `media.votredomaine.com` et validez.
   > 👉 Vous obtenez votre valeur pour : `CLOUDFLARE_R2_CUSTOM_DOMAIN=pub-xxxxxxxxxxxxxxxxxxxx.r2.dev` (ou `media.votredomaine.com`).

### Étape 2.4 — Créer le Jeton d'API R2 (Access Key & Secret Key)
1. Revenez sur la page d'accueil de **R2** (dans le menu latéral gauche).
2. Dans le panneau de droite, cliquez sur **Manage R2 API Tokens** (Gérer les jetons d'API R2).
3. Cliquez sur **Create API token** (Créer un jeton d'API).
4. Configurez le jeton :
   - **Token name** : `smart-invoice-render`
   - **Permissions** : Choisissez **Object Read & Write** (Lecture et écriture d'objets).
   - **Apply to specific buckets** : Vous pouvez cibler uniquement votre bucket `smart-invoice-media` ou tous les buckets.
   - **TTL** : Laissez vide ou définissez une date selon vos préférences de sécurité.
5. Cliquez sur **Create API Token**.
6. ⚠️ **ATTENTION :** La page suivante n'affichera la clé secrète qu'une seule fois ! Copiez immédiatement :
   - **Access Key ID** : Chaîne de 32 caractères.
     > 👉 `CLOUDFLARE_R2_ACCESS_KEY_ID=...`
   - **Secret Access Key** : Chaîne de 64 caractères hexadécimaux.
     > 👉 `CLOUDFLARE_R2_SECRET_ACCESS_KEY=...`

---

## 🚀 3. Renseigner les Variables sur Render

1. Connectez-vous sur [dashboard.render.com](https://dashboard.render.com).
2. Ouvrez votre service web Django (**Web Service**).
3. Dans le menu de gauche, cliquez sur **Environment** (Variables d'environnement).
4. Cliquez sur **Add Environment Variable** (ou **Add from .env**) et ajoutez :

```ini
CLOUDFLARE_R2_BUCKET_NAME=smart-invoice-media
CLOUDFLARE_R2_ACCOUNT_ID=<votre_account_id_cloudflare>
CLOUDFLARE_R2_ACCESS_KEY_ID=<votre_access_key_id>
CLOUDFLARE_R2_SECRET_ACCESS_KEY=<votre_secret_access_key>
CLOUDFLARE_R2_CUSTOM_DOMAIN=pub-xxxxxxxxxxxx.r2.dev
```

*(Si vous utilisez un domaine personnalisé type `media.votredomaine.com`, mettez-le dans `CLOUDFLARE_R2_CUSTOM_DOMAIN`)*.

5. Cliquez sur **Save Changes** en bas de page.
6. Render relance automatiquement un déploiement avec ces nouvelles variables.

---

## 🏗️ 4. Architecture & Fonctionnement dans le Projet

Le projet intègre nativement une gestion moderne et résiliente du stockage :

### Fichiers clés :
- `requirements.txt` : Inclut `django-storages==1.14.6` et `boto3==1.43.111`.
- `InvoiceProject/settings.py` :
  - Détecte dynamiquement la présence des variables d'environnement R2.
  - Active la classe `storages.backends.s3.S3Storage` pour le dictionnaire `STORAGES["default"]`.
  - Configure `default_acl = None` (obligatoire car R2 rejette les ACL S3).
  - Configure `signature_version = "s3v4"` et `region_name = "auto"`.
  - Configure `querystring_auth = False` lorsque le domaine public R2 ou custom domain est activé pour un accès direct et rapide.
  - Bascule automatiquement vers `django.core.files.storage.FileSystemStorage` en local si R2 n'est pas configuré.
- `InvoiceApp/views/invoices.py` :
  - La génération des factures PDF avec ReportLab gère à la fois les chemins locaux (`.path`) et les flux d'octets distants (`company.logo.open()` + `ImageReader(io.BytesIO(...))`). Le logo de l'entreprise s'affiche donc parfaitement sur les PDF générés depuis Render et stockés sur R2.

---

## ✅ 5. Vérifier que Tout Fonctionne après Déploiement

Une fois le déploiement Render terminé ("Live"), suivez ces vérifications :

### 1. Téléversement du Logo d'Entreprise
- Connectez-vous à votre application sur Render.
- Allez dans **Paramètres de l'entreprise** (`/company-settings/`).
- Uploadez une image de logo et enregistrez.
- **Résultat attendu :** L'image apparaît immédiatement dans la barre latérale et dans l'aperçu du profil.
- Faites un clic droit sur l'image > *Ouvrir l'image dans un nouvel onglet* : l'URL doit pointer vers `https://pub-xxxxxxxx.r2.dev/company_logos/...` ou votre domaine R2.

### 2. Téléversement d'une Image Produit
- Rendez-vous dans **Produits** (`/list-products/`).
- Ajoutez ou modifiez un produit en lui associant une photo.
- **Résultat attendu :** L'image du produit s'affiche correctement dans le catalogue et dans l'espace vendeur.

### 3. Contrôle dans le Tableau de Bord Cloudflare
- Retournez sur votre tableau de bord Cloudflare > **R2** > votre bucket.
- Cliquez sur **Objects**.
- **Résultat attendu :** Vous devez voir les dossiers `company_logos/` et `product_images/` contenant les fichiers téléversés.

### 4. Téléchargement d'une Facture PDF
- Créez ou ouvrez une facture existante.
- Cliquez sur **Télécharger PDF** ou **Aperçu PDF**.
- **Résultat attendu :** Le PDF se génère instantanément avec le logo de l'entreprise affiché en haut à gauche de l'en-tête.

### 5. Test de Persistance Render (Le Test Ultime)
- Dans votre tableau de bord Render, cliquez sur **Manual Deploy** > **Deploy latest commit** (ou **Clear build cache & deploy**).
- Une fois le redémarrage terminé, actualisez votre application.
- **Résultat attendu :** Les logos et images produits sont **toujours présents et visibles**, sans aucune perte de données !

---

## 🛠️ Dépannage & Questions Fréquentes

| Problème | Cause possible | Solution |
|---|---|---|
| Erreur 400 ou *Invalid Access Key* lors de l'upload | Clé d'API R2 expirée ou mal copiée | Vérifiez que vous avez bien copié les 32 caractères de l'Access Key et les 64 caractères de la Secret Key sans espaces. |
| Image brisée (carré blanc / point d'interrogation) | L'accès public du bucket n'est pas activé | Allez dans votre bucket R2 > *Settings* > *Public access* et activez *R2.dev subdomain* ou connectez un domaine. |
| Logo absent sur la facture PDF | Mauvaise lecture du flux distant | Corrigé nativement dans le projet via `ImageReader(io.BytesIO(...))` et fallback transparent. |
| Message d'erreur S3 ACL *NotImplemented* | Le client S3 tente d'envoyer un en-tête `x-amz-acl` | Vérifiez que `default_acl = None` est bien en place dans `settings.py` (déjà configuré par défaut). |
