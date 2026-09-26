"""
Revérifie auprès de MoneyFusion tous les paiements d'abonnement restés
"pending" (utile après un bug comme une mauvaise URL de vérification :
l'argent a été reçu par MoneyFusion mais le statut local n'a jamais été
mis à jour côté application).

Usage :
    python manage.py recheck_pending_payments            # applique les corrections
    python manage.py recheck_pending_payments --dry-run   # affiche sans rien modifier
"""
from django.core.management.base import BaseCommand

from InvoiceApp.models import SubscriptionPayment
from InvoiceApp.views.subscription import _verify_and_apply_payment


class Command(BaseCommand):
    help = "Revérifie les paiements MoneyFusion en attente et corrige leur statut/abonnement."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="N'applique aucune modification, affiche seulement ce qui serait fait.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        pending = SubscriptionPayment.objects.filter(
            status="pending"
        ).exclude(provider_token="").select_related("company", "company__subscription")

        total = pending.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucun paiement en attente à revérifier."))
            return

        self.stdout.write(f"{total} paiement(s) en attente trouvé(s).")

        fixed, still_pending, unreachable = 0, 0, 0

        for payment in pending:
            company_label = getattr(payment.company, "company_name", None) or payment.company.email

            if dry_run:
                self.stdout.write(f"  [dry-run] {payment.transaction_id} ({company_label}) — vérification simulée, aucune requête envoyée.")
                continue

            _verify_and_apply_payment(payment)
            payment.refresh_from_db()

            if payment.status == "success":
                fixed += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  ✔ {payment.transaction_id} ({company_label}) → payé, abonnement activé."
                ))
            elif payment.status == "failed":
                self.stdout.write(self.style.WARNING(
                    f"  ✘ {payment.transaction_id} ({company_label}) → confirmé comme échoué chez MoneyFusion."
                ))
            else:
                still_pending += 1
                unreachable += 1
                self.stdout.write(
                    f"  … {payment.transaction_id} ({company_label}) → toujours pending "
                    "(réponse MoneyFusion indisponible ou statut réellement en cours)."
                )

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nTerminé : {fixed} corrigé(s), {still_pending} toujours en attente."
            ))
            if unreachable:
                self.stdout.write(
                    "Si des paiements restent 'pending' après plusieurs essais, "
                    "vérifiez MONEYFUSION_STATUS_CHECK_TEMPLATE et les logs applicatifs "
                    "('Échec de la vérification MoneyFusion...')."
                )
