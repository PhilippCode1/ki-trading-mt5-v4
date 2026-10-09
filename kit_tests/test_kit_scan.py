"""Geheimnis-/Personendaten-Scan (tools/kit_scan.py). Synthetische Werte werden zur Laufzeit gebaut,
damit der Scan diese Testdatei selbst nicht beanstandet."""
from __future__ import annotations

import hashlib

from tools import kit_scan as ks

TOKEN = "gh" + "p_" + "A1b2C3d4" * 5
PFAD = "C:" + "\\Users\\" + "Mustermann" + "\\Downloads\\x"
LOGIN = "log" + "in = " + "51234567"
PASS = "pass" + 'word = "' + "Geheim123" + '"'


def _kat(befunde):
    return {b.kategorie for b in befunde}


def test_token_pfad_login_passwort_erkannt():
    text = "\n".join([TOKEN, PFAD, LOGIN, PASS])
    kat = _kat(ks.scan_text("x.md", text, [], oeffentlich=False))
    assert "TOKEN:GitHub-Token" in kat
    assert "BENUTZERPFAD" in kat
    assert "MT5_LOGIN" in kat
    assert "PASSWORT" in kat


def test_platzhalterpfad_und_sauberer_text_ohne_befund():
    text = "C:" + "\\Users\\" + "Benutzer" + "\\Downloads\nEin ganz normaler Satz ohne Geheimnisse, Version 1.2.3.4."
    assert ks.scan_text("x.md", text, [], oeffentlich=False) == []


def test_sperrliste_arten():
    nummer = "8" + "7654321"
    liste = [
        ks.Eintrag("benutzer", "Mustermann", "Benutzer"),
        ks.Eintrag("ersetzen", "beispiel-firma.example", "<website-domain>"),
        ks.Eintrag("geheim-hash", "sha256:" + hashlib.sha256(nummer.encode()).hexdigest(), "MT5-Login Demo"),
    ]
    text = f"Konto {nummer} bei beispiel-firma.example, Nutzer Mustermann"
    privat = _kat(ks.scan_text("x.md", text, liste, oeffentlich=False))
    assert {"GEHEIM_HASH", "BENUTZERNAME"} <= privat and "ERSETZEN" not in privat
    assert "ERSETZEN" in _kat(ks.scan_text("x.md", text, liste, oeffentlich=True))


def test_nur_geheimnisse_ignoriert_pfade():
    kat = _kat(ks.scan_text("x.md", PFAD + "\n" + TOKEN, [], oeffentlich=False, nur_geheimnisse=True))
    assert "BENUTZERPFAD" not in kat and "TOKEN:GitHub-Token" in kat


def test_ausgabe_maskiert_werte():
    b = ks.scan_text("x.md", TOKEN, [], oeffentlich=False)[0]
    assert TOKEN not in b.text() and b.maske.endswith(f"({len(TOKEN)})")


def test_eingefrorene_bereiche():
    r = ks.regeln()
    assert ks.ist_eingefroren("referenz/registers/retcodes.json", r)
    assert ks.ist_eingefroren("referenz/tests/test_t02_band.py", r)
    assert not ks.ist_eingefroren("deploy/windows-vps/40_bot.ps1", r)
    assert not ks.ist_eingefroren("docs/ARCHITEKTUR.md", r)
    assert not ks.ist_eingefroren("kit/cli.py", r)
    assert not ks.ist_eingefroren("docs/bot/ENTSCHEIDUNGEN.md", r)
    assert not ks.ist_eingefroren("docs/FAST_TRACK_PLAN.md", r)
