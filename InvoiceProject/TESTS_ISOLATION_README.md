# Tests d'isolation multi-tenant

## Fichier ajouté

`InvoiceApp/tests_multi_tenant_isolation.py` — 36 tests, 4 classes.

## Comment les lancer

```bash
python manage.py test InvoiceApp.tests_multi_tenant_isolation
```

(ou `python manage.py test` tout court pour lancer aussi `tests.py`, l'existant).

⚠️ Je n'ai pas pu exécuter ces tests moi-même dans cet environnement (pas d'accès
réseau pour installer Django). Je les ai écrits en traçant chaque appel exact du
code source de `views.py` (noms de paramètres POST, filtres `company=`, codes de
statut retournés) pour qu'ils collent au comportement réel — mais **lance-les
avant de les considérer comme validés**, et dis-moi si l'un d'eux échoue, je
corrige immédiatement.

## Ce qu'ils vérifient

Le principe de l'app : `request.user` EST l'entreprise. Toute donnée doit être
strictement cloisonnée par entreprise. Ces tests créent deux entreprises (A et B)
avec un jeu de données complet chacune, connectent le client de test en tant
qu'entreprise A, et vérifient qu'il est **impossible** — même en devinant un ID
(attaque IDOR) — de lire, modifier ou supprimer les données de B.

| Classe | Ce qui est testé |
|---|---|
| `WriteEndpointIsolationTests` | 18 tests : chaque `add_*`/`delete_*` (clients, produits, ventes, factures, paiements, fournisseurs, approvisionnements, agents, rôles, types/modes de paiement) rejette ou ignore un ID appartenant à l'autre entreprise |
| `ListViewIsolationTests` | 7 tests : dashboard et pages de liste n'affichent jamais un nom/identifiant de l'autre entreprise |
| `AiToolFunctionsIsolationTests` | 7 tests : les 5 fonctions appelées par Gemini (ventes, état financier, stock, clients, factures) restent bornées à l'entreprise connectée, même si on essaie de les détourner via leurs paramètres |
| `AiChatEndpointIsolationTests` | 4 tests : `/api/ai-chat/` bout-en-bout (avec Gemini simulé), y compris la vérification que le *résultat* renvoyé par une fonction ne contient jamais les données d'une autre entreprise |

## Verdict de la revue de code (avant même d'écrire les tests)

Bonne nouvelle : en traçant tous les points d'accès aux objets par ID dans
`views.py` (`grep` sur `.objects.get(` et `.objects.filter(`), **chaque lookup
était déjà correctement filtré par `company=request.user`** — pas de `get_object_or_404`
non scopé, pas d'oubli détecté. Ces tests ne corrigent donc pas une faille connue :
ils **verrouillent ce bon comportement existant** pour que toute modification
future qui casserait accidentellement l'isolation (ex: un nouveau développeur
qui oublie `company=request.user` dans un nouvel endpoint) fasse immédiatement
échouer la suite de tests plutôt que de passer inaperçue en production.

## Une chose repérée en passant (non corrigée, hors périmètre de cette tâche)

Dans `models.py`, `AgentRole` et `PaymentType` ont `company = models.ForeignKey(User, ..., default=1)`.
Ce `default=1` est un piège latent : si un jour du code crée un `AgentRole` ou
un `PaymentType` sans préciser explicitement `company=`, l'objet sera assigné
silencieusement à l'entreprise dont l'ID est 1, au lieu de lever une erreur.
Aujourd'hui tous les appels passent bien `company=` explicitement, donc ce n'est
pas exploité — mais je vous recommande de retirer ce `default=1` (le rendre
obligatoire) lors d'une prochaine migration, pour transformer un oubli futur en
erreur immédiate plutôt qu'en fuite de données silencieuse.
