# Déploiement sur Render

## Ce qui a été préparé

| Fichier | Rôle |
|---|---|
| `requirements.txt` | Toutes les dépendances (dont `gunicorn`, `whitenoise`, `dj-database-url`, `psycopg2-binary` ajoutées pour la prod) |
| `build.sh` | `pip install` + `collectstatic` + `migrate`, exécuté à chaque déploiement |
| `Procfile` | Commande de démarrage (`gunicorn`) |
| `render.yaml` | Blueprint : crée le Web Service + une base Postgres gratuite en un clic |
| `.env.example` | Modèle des variables d'environnement à renseigner |
| `.gitignore` | Exclut `.env`, `db.sqlite3`, `media/`, `staticfiles/`, etc. |
| `InvoiceProject/settings.py` | Modifié : WhiteNoise (statiques), `DATABASE_URL` (Postgres), `RENDER_EXTERNAL_HOSTNAME` auto-ajouté aux hôtes autorisés |

⚠️ **Points d'attention propres à Render (disque éphémère) :**
- **SQLite** : ne pas l'utiliser en prod, il serait effacé à chaque déploiement → utilisez la base **Postgres** (gratuite) créée par `render.yaml`.
- **Fichiers médias** (logos d'entreprise, images produits uploadés via `ImageField`) : eux aussi perdus à chaque déploiement sur un Web Service standard. Pour les rendre durables, deux options — un **Persistent Disk** Render (payant, simple) ou un stockage externe type **Cloudinary/S3** (gratuit, plus robuste). Dites-moi si vous voulez que je mette en place l'une des deux.

## Étapes de déploiement

### 1. Pousser le code sur GitHub
```bash
git init
git add .
git commit -m "Prêt pour déploiement Render"
git remote add origin <url-de-votre-repo>
git push -u origin main
```
Vérifiez que `db.sqlite3` et `media/` ne sont **pas** commités (le `.gitignore` s'en charge).

### 2. Créer les services sur Render

**Option A — Blueprint (recommandé, un clic)**
1. Sur [dashboard.render.com](https://dashboard.render.com), cliquez **New > Blueprint**.
2. Connectez votre repo GitHub. Render détecte `render.yaml` et propose de créer le Web Service + la base Postgres ensemble.
3. Validez. `SECRET_KEY` est généré automatiquement.

**Option B — Manuel**
1. **New > PostgreSQL** → créez une base (plan Free), notez l'**Internal Database URL**.
2. **New > Web Service** → connectez le repo.
   - Build Command : `./build.sh`
   - Start Command : `gunicorn InvoiceProject.wsgi:application --bind 0.0.0.0:$PORT`
   - Ajoutez les variables d'environnement ci-dessous manuellement.

### 3. Variables d'environnement à renseigner (Dashboard > votre service > Environment)

| Variable | Valeur |
|---|---|
| `SECRET_KEY` | générée automatiquement (Blueprint) ou une chaîne aléatoire longue |
| `DEBUG` | `False` |
| `DATABASE_URL` | l'Internal Database URL Postgres (auto-lié via `render.yaml`) |
| `ALLOWED_HOSTS` | laissez vide au premier déploiement (Render s'auto-ajoute), sinon `votre-app.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://votre-app.onrender.com` (à ajouter une fois l'URL connue) |
| `GEMINI_API_KEY` | votre clé [aistudio.google.com](https://aistudio.google.com/app/apikey) (facultatif) |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `MONEYFUSION_API_URL` | si vous utilisez les abonnements payants |
| `SITE_BASE_URL` | `https://votre-app.onrender.com` |
| `EMAIL_*` | si vous voulez de vrais emails de réinitialisation de mot de passe (sinon ils restent dans les logs) |

### 4. Premier déploiement
Render build automatiquement à chaque push. Suivez les logs : `pip install` → `collectstatic` → `migrate` → démarrage de `gunicorn`.

### 5. Créer un superutilisateur (optionnel, pour `/admin/`)
Dans le Dashboard Render, onglet **Shell** de votre Web Service :
```bash
python manage.py createsuperuser
```

### 6. Vérifications post-déploiement
- L'app répond sur `https://votre-app.onrender.com`
- Le CSS/JS s'affiche correctement (WhiteNoise sert les statiques)
- Connexion et création d'une facture fonctionnent (Postgres bien utilisé)
- Si l'assistant IA est configuré, le widget répond bien

## Limites du plan gratuit Render à connaître
- Le service **s'endort après 15 min d'inactivité** ; la requête suivante prend ~30-60s pour le réveiller.
- La base Postgres gratuite est **supprimée après 30 jours** (Render envoie un email d'alerte avant).
- Ces limites ne concernent pas les plans payants.
