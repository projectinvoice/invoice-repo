"""
Imports et dependances partagees par tous les sous-modules de vues.
Issu du decoupage de l'ancien InvoiceApp/views.py (2261 lignes -> package).
Chaque sous-module fait `from ._common import *` pour retrouver exactement
le meme environnement qu'avant (aucun changement de comportement).
"""
import json
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

import requests as http_requests

from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth, TruncDate
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdf_canvas

from django import forms

from ..models import (
    User,
    CURRENCY_CHOICES,
    AgentRole,
    Agent,
    Engine,
    Product,
    Client,
    PaymentType,
    PaymentMethod,
    Supplier,
    Supply,
    SupplyItem,
    Sale,
    SaleItem,
    Invoice,
    Payment,
    AgentStock,
    StockLoad,
    StockLoadItem,
    StockReturn,
    StockReturnItem,
    Subscription,
    SubscriptionPayment,
    SUBSCRIPTION_PLAN_CHOICES,
    SUBSCRIPTION_PLAN_PRICES,
    TRIAL_DURATION_DAYS,
    PromoCode,
    PromoCodeRedemption,
    redeem_promo_code,
)
