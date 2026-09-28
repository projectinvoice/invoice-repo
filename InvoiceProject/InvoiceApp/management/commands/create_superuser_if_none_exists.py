import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Crée un superutilisateur à partir de variables d'environnement, mais
    seulement s'il n'existe pas déjà (safe à appeler à chaque déploiement,
    par exemple depuis build.sh sur Render où le Shell interactif n'est
    pas disponible avec le plan Free).

    Variables d'environnement nécessaires :
      - DJANGO_SUPERUSER_USERNAME
      - DJANGO_SUPERUSER_EMAIL
      - DJANGO_SUPERUSER_PASSWORD

    Si l'une d'elles est absente, la commande ne fait rien (silencieusement),
    pour ne jamais faire échouer le déploiement.
    """

    help = "Crée un superutilisateur depuis les variables d'environnement s'il n'en existe pas déjà un."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

        if not (username and email and password):
            self.stdout.write(
                "create_superuser_if_none_exists : variables d'environnement "
                "manquantes, étape ignorée."
            )
            return

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Un superutilisateur existe déjà, rien à faire.")
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                f"Un utilisateur '{username}' existe déjà mais n'est pas "
                "superuser — vérifiez manuellement. Rien n'a été créé."
            )
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            company_name=os.environ.get('DJANGO_SUPERUSER_COMPANY_NAME', 'Admin'),
        )
        self.stdout.write(self.style.SUCCESS(f"Superutilisateur '{username}' créé avec succès."))
