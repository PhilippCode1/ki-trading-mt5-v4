"""Deutsche Kommandozeile: python -m kit <befehl> (Übersicht: python -m kit --help).

Betreiberbefehle `entsperren`, `pin-setzen` und `sichern --mit-schluessel` laufen nur interaktiv in der eigenen Konsole
(nie in einer Agentensitzung). `sichern` ohne Schlüssel läuft auch ohne Konsole (geplante Tagessicherung), nie beim Agenten.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from kit import __version__

ROOT = Path(__file__).resolve().parents[1]
MCP_PORTS = (22345, 22346)
MIN_FREI_GB = 15


def _ausgabe_utf8() -> None:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def lauschende_ports(netstat: Callable[[], str] | None = None) -> set[int]:
    """Lokale TCP-Ports im Zustand LISTENING (Windows: netstat -ano), ohne selbst eine Verbindung aufzubauen."""
    if netstat is None:
        if platform.system() != "Windows":
            return set()

        def netstat() -> str:
            return subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, check=False,
                                  errors="replace").stdout
    ports: set[int] = set()
    for zeile in netstat().splitlines():
        teile = zeile.split()
        if len(teile) >= 4 and teile[0].upper() == "TCP" and teile[3].upper() in {"LISTENING", "ABHÖREN"}:
            lokal = teile[1]
            try:
                ports.add(int(lokal.rsplit(":", 1)[1]))
            except (IndexError, ValueError):
                continue
    return ports


def globales_mt5_vorhanden(lauf: Callable[[list[str]], int] | None = None) -> bool | None:
    """True, wenn das globale Python 3.11 MetaTrader5 importieren kann (Agenten-Umgehung möglich); None = nicht prüfbar."""
    if platform.system() != "Windows" or shutil.which("py") is None:
        return None
    befehl = ["py", "-3.11", "-I", "-c", "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('MetaTrader5') else 3)"]
    if lauf is None:
        def lauf(cmd: list[str]) -> int:
            return subprocess.run(cmd, capture_output=True, check=False).returncode
    code = lauf(befehl)
    if code == 0:
        return True
    if code == 3:
        return False
    return None


def pruefen(*, ports: set[int] | None = None, globales_mt5: bool | None = None, frei_gb: float | None = None) -> list[tuple[str, str]]:
    """Umgebungsprüfung; liefert (Stufe, Text) mit Stufe OK/WARNUNG/FEHLER."""
    erg: list[tuple[str, str]] = []
    v = sys.version_info
    erg.append(("OK" if v >= (3, 11) else "FEHLER", f"Python {v.major}.{v.minor}.{v.micro}"))
    if frei_gb is None:
        frei_gb = shutil.disk_usage(ROOT).free / 1e9
    erg.append(("OK" if frei_gb >= MIN_FREI_GB else "WARNUNG", f"Freier Speicher {frei_gb:.1f} GB (Ziel ≥ {MIN_FREI_GB} GB)"))
    if ports is None:
        ports = lauschende_ports()
    offen = sorted(p for p in MCP_PORTS if p in ports)
    erg.append(("FEHLER", f"MT5-KI/MCP-Server lauschen auf {offen} – vor jedem Schreibmodus abschalten (Plan §3)")
               if offen else ("OK", "MT5-KI/MCP-Ports 22345/22346 geschlossen"))
    if globales_mt5 is None:
        globales_mt5 = globales_mt5_vorhanden()
    if globales_mt5 is True:
        erg.append(("FEHLER", "MetaTrader5 ist im globalen Python 3.11 installiert – entfernen (Plan §3), Bot nur aus .venv-bot"))
    elif globales_mt5 is False:
        erg.append(("OK", "MetaTrader5 nicht im globalen Python 3.11"))
    else:
        erg.append(("WARNUNG", "globales Python 3.11 nicht prüfbar"))
    if installiert():
        erg.append(("OK", "Installierte Kopie (Agent-Wächter wurde bei der Installation im Repo geprüft)"))
        return erg
    einstellungen = ROOT / ".claude" / "settings.json"
    try:
        hook_ok = "agent_waechter.py" in json.dumps(json.loads(einstellungen.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        hook_ok = False
    erg.append(("OK", "Agent-Wächter in .claude/settings.json eingetragen") if hook_ok
               else ("FEHLER", "Agent-Wächter fehlt in .claude/settings.json"))
    if hook_ok:
        from kit import bedienung, paths
        try:
            luecke = bedienung.waechter_luecke(ROOT)
        except paths.AblageFehler as exc:
            luecke = f"Laufzeitablage nicht ermittelbar: {exc}"
        erg.append(("WARNUNG", f"Agent-Wächter schützt die Laufzeitablage nicht ({luecke}) – docs/bot/waechter_patch.diff "
                               "einspielen (nur Betreiber); bis dahin keine neue Installation") if luecke
                   else ("OK", "Agent-Wächter sperrt die Laufzeitablage"))
    return erg


def installiert() -> bool:
    """Läuft dieser Code aus <Ablage>\\app\\<tag> (unveränderliche Installation mit INSTALLATION.json)?"""
    from kit import paths
    try:
        return ROOT.parent == paths.kit_home() / "app" and (ROOT / "INSTALLATION.json").is_file()
    except paths.AblageFehler:
        return False


def installation_veraendert() -> str | None:
    """Läuft dieser Code aus einer Installation, muss ihr mechanik_hash noch dem Wert bei der Installation entsprechen –
    auch beim Start über start_<modus>.cmd bzw. die Autostart-Hülle (nicht nur über kit starten)."""
    if not installiert():
        return None
    from kit.gates.tor_t import mechanik_hash
    try:
        soll = json.loads((ROOT / "INSTALLATION.json").read_text(encoding="utf-8")).get("mechanik_hash")
    except (OSError, ValueError):
        return "INSTALLATION.json unlesbar"
    if mechanik_hash(ROOT) != soll:
        return "Installation verändert (mechanik_hash weicht von INSTALLATION.json ab) – neu installieren"
    return None


def _terminal(konf):
    from kit import paths
    from kit.broker.mt5_real import Mt5Terminal
    return Mt5Terminal(pfad=konf.terminal_pfad or None, schluessel_ordner=paths.kit_home() / "geheim")


def _zeige(titel: str, daten: object) -> None:
    print(f"== {titel}")
    print(json.dumps(daten, ensure_ascii=False, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    _ausgabe_utf8()
    ap = argparse.ArgumentParser(prog="python -m kit", description="KI-Trading MT5 – schlanker Demo-Bot (nur DEMO)")
    sub = ap.add_subparsers(dest="befehl", required=True)
    sub.add_parser("version", help="Version ausgeben")
    sub.add_parser("pruefen", help="Umgebung prüfen (MCP-Ports, globales MetaTrader5, Speicher, Wächter)")
    sub.add_parser("rauchtest", help="nur lesend: Terminal, Konto-Modi, Symbolverträge, Serverversatz")
    dz = sub.add_parser("daten-ziehen", help="nur lesend: Kerzen der Entwicklungsperiode in SQLite unter <Ablage>\\marktdaten")
    dz.add_argument("--holdout", action="store_true", help="nur mit HOLDOUT-OK des Betreibers (Lauf F-06)")
    dz.add_argument("--fehlende", action="store_true", help="nur Symbole/Zeitrahmen ohne OK-Abzug dieses Zeitraums")
    sub.add_parser("konto-registrieren", help="aktuelles DEMO-Konto in die Demo-Allowlist (nur HMAC-Abdruck)")
    pr = sub.add_parser("probe", help="Demo-Probe: einzel (ein Zyklus) oder skripte (D-Skripte/Killer-Tests, beaufsichtigt)")
    pr.add_argument("art", choices=["einzel", "skripte"])
    pr.add_argument("--schreiben", action="store_true", help="ohne diesen Schalter wird nichts gesendet")
    pr.add_argument("--symbol")
    pr.add_argument("--nur", help="Skripte, z. B. D-01,D-10")
    pr.add_argument("--wiederholen", type=int, default=1)
    la = sub.add_parser("lauf", help="Takt starten: --modus probe (Technik-Messung) | demo (erst nach F-06/F-07)")
    la.add_argument("--modus", choices=["probe", "demo"], required=True)
    la.add_argument("--schreiben", action="store_true", help="ohne diesen Schalter startet nichts")
    la.add_argument("--dauer-min", type=float)
    st = sub.add_parser("stop", help="Kill-Stufe setzen (STOP-Datei) oder den Takt beenden")
    st.add_argument("--modus", choices=["probe", "demo"], default="probe")
    g = st.add_mutually_exclusive_group(required=True)
    g.add_argument("--k1", action="store_true", help="keine Einstiege (vorübergehend)")
    g.add_argument("--k2", action="store_true", help="keine Einstiege, dauerhaft (Aufheben nur mit PIN)")
    g.add_argument("--k3", action="store_true", help="alle eigenen Positionen schließen + K2 (Aufheben nur mit PIN)")
    g.add_argument("--beenden", action="store_true", help="Takt geordnet beenden (Positionen behalten Server-SL/TP)")
    g.add_argument("--k1-aufheben", action="store_true", help="K1 aufheben (K2/K3 nur per kit entsperren)")
    sa = sub.add_parser("status", help="Zustand, Sperren, letzte Meldungen (redigiert, nur lesend)")
    sa.add_argument("--modus", choices=["probe", "demo", "trocken"], default="probe")
    tt = sub.add_parser("tor-t", help="Tor T – Technik-Stand aus dem Journal (nur lesend)")
    tt.add_argument("--stand", action="store_true", required=True)
    tt.add_argument("--modus", choices=["probe", "demo"], default="probe")
    tx = tt.add_mutually_exclusive_group()
    tx.add_argument("--ohne-export", action="store_true", help="nur anzeigen, keine Exportdatei (für den 15-min-Status)")
    tx.add_argument("--zertifikat", action="store_true",
                    help="bei BESTANDEN: Zertifikat berichte/tor_t/<datum>.json aus einem frischen Export (sauberer Commit nötig)")
    en = sub.add_parser("entsperren", help="NUR BETREIBER: Sperre mit PIN aufheben (interaktiv)")
    en.add_argument("--modus", choices=["probe", "demo"], default="probe")
    en.add_argument("--grund", required=True,
                    help="K2, K3, LOSS_LOCK, STOP50, STOP_OUT, NULLTOLERANZ, NICHT_DEMO, ZUSTAND, SYMBOL:<Symbol> oder ALLE")
    sub.add_parser("pin-setzen", help="NUR BETREIBER: PIN festlegen/ändern (interaktiv)")
    ins = sub.add_parser("installieren", help="getaggten Stand nach <Ablage>\\app\\<tag> installieren")
    ins.add_argument("--tag", required=True)
    sn = sub.add_parser("starten", help="installierte Kopie losgelöst starten (Technik-Messung): --tag <tag> --modus probe")
    sn.add_argument("--tag", required=True)
    sn.add_argument("--modus", choices=["probe", "demo"], default="probe")
    sn.add_argument("--dauer-min", type=float)
    um = sub.add_parser("umziehen", help="einmalig: Laufzeitdaten aus %%LOCALAPPDATA%%\\kit in die feste Ablage im Benutzerprofil "
                                         "kopieren (setzt Abbrüche fort, überschreibt nie)")
    um.add_argument("--von", help="alte Ablage, falls mehrere gefunden werden")
    um.add_argument("--abschliessen", action="store_true",
                    help="abgebrochenen Umzug ohne erreichbare Quelle fail-closed abschließen (K2, Aufheben nur mit PIN)")
    wh = sub.add_parser("wiederherstellen", help="Sicherung (ZIP aus kit sichern) übernehmen – nie überschreiben, Sperren übernehmen")
    wh.add_argument("--aus", required=True, help="Pfad zur kit-sicherung-*.zip")
    si = sub.add_parser("sichern", help="Journale, Zustände, Freigaben, Exporte als ZIP sichern – nie in einer Agentensitzung; "
                                        "--mit-schluessel nur interaktiv beim Betreiber")
    si.add_argument("--ziel", required=True)
    si.add_argument("--mit-schluessel", action="store_true")
    tl = sub.add_parser("trockenlauf", help="kompletter Takt gegen die MT5-Attrappe mit beschleunigter Uhr (kein Terminal)")
    tl.add_argument("--tage", type=float, default=7.0)
    tl.add_argument("--schritt-s", type=float, default=1.0)
    fo = sub.add_parser("forschung", help="Forschung F-04/F-05 (offline, nur Entwicklungsdaten): vorab | kostenprofil | entwicklung | "
                                          "pruefen | aenderung (Runde 2: python -m forschung.runde2 in .venv-forschung)")
    fo.add_argument("schritt", choices=["vorab", "kostenprofil", "entwicklung", "pruefen", "aenderung"])
    fo.add_argument("--dateien", help="nur aenderung: geänderte, committete Repo-Dateien, kommagetrennt")
    fo.add_argument("--grund", help="nur aenderung: Grund der Werkzeugänderung nach der Datensicht")
    fo.add_argument("--lauf", default="F-04")
    fo.add_argument("--prereg-ok", help="Freigabezeile PREREG-OK aus dem Laufprompt (nur vorab)")
    fo.add_argument("--datum", help="Datum JJJJ-MM-TT (Standard: heute, UTC)")
    fo.add_argument("--prozesse", type=int, help="parallele Läufe (Standard: Kerne − 4)")
    a = ap.parse_args(argv)
    if a.befehl == "version":
        print(f"kit {__version__}")
        return 0
    if a.befehl == "pruefen":
        ergebnisse = pruefen()
        for stufe, text in ergebnisse:
            print(f"{stufe:8} {text}")
        return 1 if any(s == "FEHLER" for s, _ in ergebnisse) else 0
    if a.befehl == "forschung":
        return _forschung(a)
    if a.befehl in ("probe", "lauf") and not a.schreiben:
        print("Ohne --schreiben wird nichts gesendet.")
        return 2
    if a.befehl in ("stop", "status", "tor-t", "entsperren", "pin-setzen", "installieren", "starten", "sichern", "trockenlauf", "wiederherstellen",
                    "umziehen"):
        return _ohne_terminal(a)
    from kit import betrieb, config, paths, umzug
    from kit.broker.seam import BrokerFehler
    from kit.live_guard import LiveGesperrt
    try:
        umzug.pruefen()                                  # vor dem ersten Terminalzugriff (der legt geheim/ in der Ablage an)
    except paths.AblageFehler as exc:
        print(f"Nicht ausgeführt: {exc}")
        return 1
    if a.befehl in ("probe", "lauf"):
        grund = installation_veraendert()
        if grund:
            print(f"Schreibmodus verweigert: {grund}")
            return 2                                     # Sicherheits-Ende: die Autostart-Hülle startet nicht neu
    konf = config.laden()
    term = _terminal(konf)
    try:
        return _ausfuehren(a, konf, term, betrieb, paths)
    except BrokerFehler as exc:
        print(f"MT5 nicht nutzbar: {exc}")
        if "Authorization" in str(exc):
            print("→ Im MT5-Terminal mit einem gültigen DEMO-Konto anmelden (Datei → Bei Handelskonto anmelden bzw. Datei → "
                  "Konto eröffnen → Demo). Das darf nur der Betreiber; der Bot fragt nie nach Zugangsdaten.")
        return 4
    except LiveGesperrt as exc:
        print(f"Gesperrt: {exc}")
        return 5
    except paths.AblageFehler as exc:
        print(f"Nicht ausgeführt: {exc}")
        return 1
    finally:
        term.trennen()


def _ausfuehren(a, konf, term, betrieb, paths) -> int:
    if a.befehl == "rauchtest":
        erg = betrieb.rauchtest(term, konf)
        _zeige("Rauchtest (redigiert)", erg)
        print(f"Export: {betrieb.export_schreiben('rauchtest', erg)}")
        return 0
    if a.befehl == "daten-ziehen":
        erg = betrieb.daten_ziehen(term, konf, paths.kit_home() / "marktdaten" /
                                   ("holdout.sqlite" if a.holdout else "entwicklung.sqlite"), holdout_frei=a.holdout,
                                   nur_fehlende=a.fehlende)
        _zeige("Datenabzug (nur Kennzahlen)", erg)
        return 0 if all(z["status"] == "OK" for z in erg) else 3
    if a.befehl == "konto-registrieren":
        print(f"Demokonto registriert (Abdruck {betrieb.konto_registrieren(term)}).")
        return 0
    if a.befehl in ("probe", "lauf"):
        fehler = [t for s, t in pruefen() if s == "FEHLER"]
        if fehler:
            print("Schreibmodus verweigert:\n  " + "\n  ".join(fehler))
            return 1
        if a.befehl == "lauf":
            return betrieb.lauf(term, konf, a.modus, dauer_min=a.dauer_min)
        if a.art == "skripte":
            erg = betrieb.skripte(term, konf, symbol=a.symbol, nur=a.nur.split(",") if a.nur else None, wiederholen=a.wiederholen)
            _zeige("Skripte (redigiert)", [{k: v for k, v in e.items() if k != "schritte"} for e in erg])
            print(f"Export: {betrieb.export_schreiben('skripte', erg)}")
            return 0 if all(e["urteil"] != "FAIL" for e in erg) else 6
        _zeige("Einzelprobe (redigiert)", betrieb.probe_einzel(term, konf, symbol=a.symbol))
        return 0
    return 2


def _agentensitzung() -> bool:
    return bool(os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"))


def _interaktiv() -> str | None:
    if _agentensitzung():
        return "Dieser Befehl ist dem Betreiber vorbehalten und läuft nie in einer Agentensitzung."
    if not sys.stdin.isatty():
        return "Nur interaktiv in der eigenen Konsole des Betreibers."
    return None


def _ohne_terminal(a) -> int:
    from kit import bedienung, umzug
    from kit.live_guard import LiveGesperrt
    from kit.paths import AblageFehler
    from kit.state.journal import JournalFehler
    from kit.state.pin import PinFehler
    from kit.state.store import SchreiberAktiv
    try:
        if a.befehl == "stop":
            stufe = 1 if a.k1 else 2 if a.k2 else 3 if a.k3 else 0
            print(bedienung.stop(a.modus, stufe=stufe, beenden=a.beenden, k1_aufheben=a.k1_aufheben))
            return 0
        if a.befehl == "status":
            _zeige(f"Status {a.modus} (redigiert)", bedienung.status(a.modus))
            return 0
        if a.befehl == "tor-t":
            if a.ohne_export:
                _zeige("Tor T (redigiert)", {k: v for k, v in bedienung.tor_t_stand(a.modus).items() if k != "kills"})
                return 0
            if a.zertifikat:
                stand, json_pfad, md_pfad = bedienung.tor_t_zertifikat(a.modus)
                _zeige("Tor T (redigiert)", {k: v for k, v in stand.items() if k != "kills"})
                print(f"Zertifikat: {json_pfad.name}, {md_pfad.name} (berichte/tor_t)")
                return 0
            stand, pfad = bedienung.tor_t_bericht(a.modus)
            _zeige("Tor T (redigiert)", {k: v for k, v in stand.items() if k != "kills"})
            print(f"Export: {pfad}")
            return 0
        if a.befehl == "installieren":
            print(f"Installiert: {bedienung.installieren(a.tag)}")
            return 0
        if a.befehl == "starten":
            pid = bedienung.starten(a.tag, a.modus, dauer_min=a.dauer_min)
            print(f"Gestartet (Prozess {pid}). Stoppen: kit stop --beenden --modus {a.modus}; Zustand: kit status --modus {a.modus}")
            return 0
        if a.befehl == "umziehen":
            _zeige("Umzug der Laufzeitdaten", umzug.abschliessen() if a.abschliessen else
                   umzug.umziehen(Path(a.von) if a.von else None))
            return 0
        if a.befehl == "trockenlauf":
            return _trockenlauf(a)
        if a.befehl == "wiederherstellen":
            _zeige("Wiederherstellung", umzug.wiederherstellen(Path(a.aus)))
            return 0
        if a.befehl == "sichern" and not a.mit_schluessel and not _agentensitzung():
            print(f"Sicherung: {bedienung.sichern(Path(a.ziel))}")      # geplante Tagessicherung (Aufgabe des Bot-Benutzers)
            return 0
        grund = _interaktiv()                            # ab hier nur der Betreiber in seiner Konsole
        if grund:
            print(grund)
            return 7
        if a.befehl == "sichern":                        # Sicherungen enthalten Rohjournale und ggf. Schlüssel
            print(f"Sicherung: {bedienung.sichern(Path(a.ziel), mit_schluessel=a.mit_schluessel)}")
            return 0
        if a.befehl == "pin-setzen":
            print(bedienung.pin_setzen())
            return 0
        print(bedienung.entsperren(a.modus, a.grund))
        return 0
    except (bedienung.BedienFehler, umzug.UmzugFehler, PinFehler, SchreiberAktiv, LiveGesperrt, AblageFehler, JournalFehler) as exc:
        print(f"Nicht ausgeführt: {exc}")
        return 1


def _trockenlauf(a) -> int:
    import datetime as dt

    from kit import bedienung, paths
    from kit.run import trockenlauf
    ablage = paths.ablage("trocken") / f"{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}"
    erg = trockenlauf.laufen(ablage, tage=a.tage, schritt_s=a.schritt_s)
    daten = {**{k: v for k, v in erg.__dict__.items() if k != "tor_t"}, "tor_t": {k: v for k, v in erg.tor_t.items() if k != "kills"},
             "ok": erg.ok}
    _zeige("Trockenlauf", daten)
    print(f"Export: {bedienung.export('trockenlauf', daten)}")
    return 0 if erg.ok else 6


def _forschung(a) -> int:
    """Versuchsprotokoll (alle Läufe) und Entwicklungsauswertung F-04 – liest nur <Ablage>/marktdaten/entwicklung.sqlite, nie den Holdout.
    --lauf wählt die Runde für vorab und aenderung (F-04, F-05); pruefen prüft alle vorregistrierten Läufe."""
    import datetime as dt

    from kit.paths import AblageFehler
    from kit.research import daten, entwicklung, protokoll
    datum = a.datum or dt.datetime.now(dt.UTC).date().isoformat()
    try:
        if a.schritt == "vorab":
            if not a.prereg_ok:
                print("Nicht ausgeführt: --prereg-ok \"<Freigabezeile aus dem Laufprompt>\" fehlt.")
                return 2
            eintraege = protokoll.vorab(a.lauf, a.prereg_ok, datum)
            _zeige("Vorregistrierung im Versuchsprotokoll", [{"seq": e["seq"], "familie": e["body"]["family"], "commit": e["body"]["commit"][:12]}
                                                            for e in eintraege])
            return 0
        if a.schritt == "pruefen":
            befunde = protokoll.pruefen()
            offen = [f"{lauf}:{x}" for lauf in protokoll.laeufe() for x in protokoll.vollstaendigkeit(lauf=lauf)]
            urteil = "BEFUNDE" if befunde else ("UNVOLLSTAENDIG" if offen else "VERIFIZIERT")
            _zeige("Versuchsprotokoll", {"eintraege": len(protokoll.lesen()), "befunde": befunde, "fehlt": offen, "urteil": urteil})
            return 0 if urteil == "VERIFIZIERT" else 6
        if a.schritt == "aenderung":
            if not a.dateien or not a.grund:
                print("Nicht ausgeführt: --dateien und --grund nötig.")
                return 2
            e = protokoll.aenderung_nach_sicht([d.strip() for d in a.dateien.split(",") if d.strip()], a.grund, datum, lauf=a.lauf)
            _zeige("Werkzeugänderung nach der Datensicht", {"seq": e["seq"], "variante": e["body"]["variant_id"],
                                                             "commit": e["body"]["commit"][:12], "dateien": sorted(e["body"]["code"])})
            return 0
        if a.schritt == "kostenprofil":
            _zeige("Kostenprofil (erste Datensicht, nur Kennzahlen)", entwicklung.kostenprofil_eintragen(datum=datum))
            return 0
        erg = entwicklung.ausfuehren(datum=datum, prozesse=a.prozesse)
        _zeige("Entwicklungsauswertung", erg)
        return 0
    except (protokoll.ProtokollFehler, daten.DatenFehler, daten.HoldoutGesperrt, AblageFehler) as exc:
        print(f"Nicht ausgeführt: {exc}")
        return 1
