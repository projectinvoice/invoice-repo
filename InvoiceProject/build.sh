#!/usr/bin/env bash
# Script de build exécuté par Render avant chaque démarrage du service.
# Configuré comme "Build Command" dans les paramètres du Web Service
# (ou automatiquement si vous utilisez render.yaml).
set -o errexit  # arrête le script à la première erreur

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate

# Crée un superutilisateur si aucun n'existe (utile car le Shell interactif
# n'est pas disponible sur le plan Free de Render). Ne fait rien si les
# variables DJANGO_SUPERUSER_* ne sont pas définies.
python manage.py create_superuser_if_none_exists
