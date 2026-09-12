#!/usr/bin/env bash
# Script de build exécuté par Render avant chaque démarrage du service.
# Configuré comme "Build Command" dans les paramètres du Web Service
# (ou automatiquement si vous utilisez render.yaml).
set -o errexit  # arrête le script à la première erreur

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate
