#!/usr/bin/env python3
"""Registra fixtures/catalog.json dalla House of Journeys API in locale `it`.

Uso:
  record_catalog.py --raw-dir DIR --dry-run     # stampa le chiamate previste, nessuna rete
  record_catalog.py --raw-dir DIR               # registra in DIR (nuova o vuota), scrive la fixture
  record_catalog.py --raw-dir DIR --build-only  # ricostruisce la fixture da DIR senza chiamate

La chiave viene letta SOLO dalle variabili d'ambiente HOFJ_API_KEY (o API_BEAR_KEY) e non
viene mai stampata né salvata. DIR sta FUORI dal repository: contiene le risposte grezze
salvate da api_explore.Client, così la fixture si può ricostruire senza consumare quota.

Solo stdlib, compatibile con Python 3.7.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_explore  # noqa: E402

LOCALE = "it"
PAGE_LIMIT = api_explore.PAGE_LIMIT
KEY_ENVS = ("HOFJ_API_KEY", "API_BEAR_KEY")
BRAND_ENV = "HOFJ_BRAND"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures",
                           "catalog.json")
EXPECTED_TOTAL = 123   # docs/api/counts.md (locale en): stima usata dal dry-run
EXPECTED_ACTIVE = 92
# chiavi scartate a ogni profondità del dettaglio: immagini e programma di viaggio
MEDIA_KEYS = frozenset(["gallery", "image", "images", "cover", "media", "travelProgram"])
# campi di RF-28 presi pari pari dal dettaglio (category, venue, destination, hotels a parte)
CATALOG_FIELDS = ("id", "title", "slug", "shortDescription", "price", "currency", "minPax",
                  "maxPax", "minDate", "maxDate", "availabilities", "defaultDurationInDays",
                  "updatedAt")


def strip_media(value):
    """Copia ricorsiva di `value` senza le chiavi in MEDIA_KEYS. Non modifica l'input."""
    if isinstance(value, dict):
        return {k: strip_media(v) for k, v in value.items() if k not in MEDIA_KEYS}
    if isinstance(value, list):
        return [strip_media(v) for v in value]
    return value


def project_detail(detail):
    """Campi di RF-28 presi dal dettaglio esteso, con i nomi dell'API; None se mancanti."""
    catalog = {k: detail.get(k) for k in CATALOG_FIELDS}
    catalog["category"] = detail.get("category")
    catalog["venue"] = detail.get("venue")
    catalog["destination"] = detail.get("destination")
    raw_attributes = detail.get("rawAttributes") or {}
    catalog["hotels"] = strip_media(raw_attributes.get("hotels"))
    return catalog
