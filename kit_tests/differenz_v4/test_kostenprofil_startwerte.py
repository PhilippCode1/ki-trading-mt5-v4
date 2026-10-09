"""Die Startwerte des Kostenprofils (config/kostenprofil/f04_startwerte.json, privat) stimmen mit dem Referenzregister
referenz/registers/cost_truth.json überein: Kommission 3,25 EUR je Lot und Seite und Swappunkte desselben Standardprofils
(Rohspread-Konto in EUR). Privat: beide Dateien liegen nicht im Spiegel."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from kit.backtest.kosten import Kostenprofil
from kit.research import entwicklung

pytestmark = pytest.mark.privat
ROOT = Path(__file__).resolve().parents[2]


def test_startwerte_gleich_register():
    roh = (ROOT / "referenz" / "registers" / "cost_truth.json").read_bytes()
    reg = json.loads(roh)
    sw = json.loads((ROOT / "config" / "kostenprofil" / "f04_startwerte.json").read_text(encoding="utf-8"))
    assert sw["quelle_sha256"] == hashlib.sha256(roh).hexdigest()
    profil = [a for a in reg["accounts"] if a.get("default") and a["variant"] == "RAW" and a["account_ccy"] == "EUR"
              and "commission" in a and str(a["commission"]["value"]) == sw["provision_gegenprobe"] and a["commission"]["currency"] == "EUR"]
    assert len(profil) == 1
    swaps = {p["symbol_id"].split("-")[-1]: [p["swap_points"]["long"], p["swap_points"]["short"]]
             for p in reg["products"] if p["profile_id"] == profil[0]["id"]}
    assert {s: swaps[s] for s in sw["swap_punkte"]} == sw["swap_punkte"] and len(sw["swap_punkte"]) == 7
    assert sw["provision_gemessen"] == "0" and sw["dreifachtag"] == int(profil[0]["swap_triple_weekday"]["value"])


def test_kostenprofile_der_auswertung():
    sw = entwicklung.startwerte()
    haupt, x15, gegen = (entwicklung.kostenprofil(p, sw) for p in entwicklung.PROFILE)
    assert isinstance(haupt, Kostenprofil) and haupt.provision() == 0 and gegen.provision() == 3.25
    assert x15.faktor == 1.5 and x15.spread_points(3) == 5 and haupt.spread_points(3) == 3
    assert haupt.dreifachtag == gegen.dreifachtag == 2 and haupt.swap_punkte == gegen.swap_punkte == x15.swap_punkte
