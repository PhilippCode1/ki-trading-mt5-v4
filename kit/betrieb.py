"""Betriebsfunktionen der CLI (F-02): Rauchtest (nur lesen), Datenabzug (nur lesen), Konto-Registrierung, Einzelprobe (DEMO).

Alle Ausgaben sind redigiert: keine Login-Nummer, kein Server-, Firmen- oder Kontoname, keine Kontostände.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from kit import live_guard, paths, umzug
from kit.broker.readonly import ReadOnlyTerminal
from kit.config import Konfiguration
from kit.domain import rounding
from kit.domain.types import Absicht, Action, Namensraum, OpStatus, Side
from kit.orders import ids
from kit.research import daten
from kit.state.store import Schreibsperre

UTC = dt.UTC


def rauchtest(terminal, konf: Konfiguration, *, versatz_messen: bool = True) -> dict:
    """Nur lesend: Terminal, Konto-Modi, Symbolverträge, Serverversatz. send/check sind technisch verboten."""
    ro = ReadOnlyTerminal(terminal)
    info = terminal.verbinden()
    konto = ro.account()
    erg: dict = {"zeit_utc": dt.datetime.now(UTC).isoformat(timespec="seconds"), "terminal": {k: info.get(k) for k in
                 ("build", "connected", "trade_allowed", "tradeapi_disabled", "maxbars")}, "konto": {"handelsmodus": str(konto.trade_mode),
                 "kontomodus": str(konto.margin_mode), "waehrung": konto.currency, "hebel": konto.leverage,
                 "handel_erlaubt": konto.trade_allowed}, "symbole": {}, "versatz_stunden": None, "befunde": []}
    for sym in dict.fromkeys(konf.strategie_symbole + konf.probe_symbole):
        name = konf.broker_name(sym)
        try:
            s = ro.symbol(name)
            q = ro.quote(name)
            erg["symbole"][sym] = {"name": s.name, "digits": s.digits, "point": str(s.point), "tick_size": str(s.tick_size),
                                   "tick_value": str(s.tick_value), "kontrakt": str(s.contract_size), "vol_min": str(s.volume_min),
                                   "vol_schritt": str(s.volume_step), "vol_max": str(s.volume_max), "stops_level": s.stops_level,
                                   "freeze_level": s.freeze_level, "fuellart": s.filling, "handelsmodus": s.trade_mode,
                                   "spread_points": int((q.ask - q.bid) / s.point), "waehrung_gewinn": s.currency_profit}
        except Exception as exc:  # noqa: BLE001
            erg["symbole"][sym] = {"fehler": str(exc)}
            erg["befunde"].append(f"{sym}: {exc}")
    if versatz_messen:
        try:
            erg["versatz_stunden"] = terminal.messe_versatz(konf.broker_name(konf.probe_symbole[0])) / 3600
        except Exception as exc:  # noqa: BLE001
            erg["befunde"].append(f"Serverversatz: {exc}")
    if konto.trade_mode.value != "DEMO":
        erg["befunde"].append(f"Konto ist {konto.trade_mode} – der Bot schreibt nur auf DEMO.")
    if konto.margin_mode.value != "HEDGING":
        erg["befunde"].append("Konto ist kein Hedging-Konto – Plan verlangt Hedging (Positionen sonst verschmolzen).")
    if not info.get("trade_allowed"):
        erg["befunde"].append("Algo Trading ist am Terminal aus (Knopf „Algo Trading“ in der Symbolleiste einschalten).")
    if info.get("tradeapi_disabled"):
        erg["befunde"].append("Terminal sperrt Handel über die Python-API (Extras → Optionen → Expert Advisors: Haken bei "
                              "„Algorithmischen Handel über externe Python-API deaktivieren“ entfernen).")
    if not konto.trade_allowed and info.get("trade_allowed") and not info.get("tradeapi_disabled"):
        erg["befunde"].append("Konto erlaubt keinen Algo-Handel (z. B. mit Investor-Passwort angemeldet) – mit dem "
                              "Handelspasswort anmelden.")
    gewinn = {erg["symbole"][s].get("waehrung_gewinn") for s in erg["symbole"] if "fehler" not in erg["symbole"][s]}
    for w in sorted(g for g in gewinn if g and g != konto.currency):
        kandidaten = [konf.broker_name(konto.currency + w), konf.broker_name(w + konto.currency)]
        if not any(_lesbar(ro, k) for k in kandidaten):
            erg["befunde"].append(f"Kein Umrechnungskurs {konto.currency}/{w} lesbar ({' oder '.join(kandidaten)}) – Symbole mit "
                                  f"Gewinnwährung {w} werden nie eröffnet (ggf. [symbol_namen] ergänzen).")
    if info["maxbars"] and info["maxbars"] < 1_000_000:
        erg["befunde"].append(f"„Max. Balken“ = {info['maxbars']} – für lange H1-Historie auf „Unbegrenzt“ stellen.")
    return erg


def _lesbar(ro, name: str) -> bool:
    try:
        ro.symbol(name)
        ro.quote(name)
        return True
    except Exception:  # noqa: BLE001
        return False


TF_S = {"D1": 86400, "H4": 14400, "H1": 3600}


def _vorhandene(db_pfad: Path, start: str, ende: str) -> dict[tuple[str, str], str]:
    """(Symbol, Zeitrahmen) → erster Balken der jüngsten OK-Abzüge desselben Zeitraums (für --fehlende)."""
    import sqlite3
    if not db_pfad.exists():
        return {}
    con = sqlite3.connect(db_pfad)
    try:
        zeilen = con.execute("SELECT symbol, zeitrahmen, erster FROM abzug WHERE status = 'OK' AND start = ? AND ende = ? ORDER BY id",
                             (start, ende)).fetchall()
    finally:
        con.close()
    return {(s, tf): erster for s, tf, erster in zeilen}


def daten_ziehen(terminal, konf: Konfiguration, db_pfad: Path, *, holdout_frei: bool = False, nur_fehlende: bool = False) -> list[dict]:
    """Je Symbol und Zeitrahmen ein Abzug; ein Fehler betrifft nur seine Zeile. MT5 liefert Historie nur so weit zurück, wie
    „Max. Balken“ ab heute reicht – reicht es für den Anfang des Zeitraums nicht, heißt die Zeile MAXBARS_ZU_KLEIN."""
    from kit.broker.seam import BrokerFehler
    ro = ReadOnlyTerminal(terminal)
    info = terminal.verbinden()
    start, ende = konf.holdout if holdout_frei else konf.entwicklung
    start_s = dt.datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp()
    maxbars = int(info.get("maxbars") or 0)
    vorhanden = _vorhandene(db_pfad, start, ende) if nur_fehlende else {}
    out = []
    for sym in konf.strategie_symbole:
        name = konf.broker_name(sym)
        erster = None
        for tf in dict.fromkeys(("D1", *konf.zeitrahmen)):
            if (name, tf) in vorhanden:
                if tf == "D1" and vorhanden[(name, tf)]:
                    erster = int(dt.datetime.strptime(vorhanden[(name, tf)], "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())
                out.append({"symbol": sym, "tf": tf, "status": "VORHANDEN"})
                continue
            benoetigt = int((time.time() - start_s) / TF_S.get(tf, 3600) * 5 / 7 * 1.03)      # Handelstage bis heute
            if maxbars and benoetigt > maxbars:
                out.append({"symbol": sym, "tf": tf, "anzahl": 0, "status": "MAXBARS_ZU_KLEIN",
                            "hinweis": f"braucht ≈ {benoetigt} Balken ab heute, „Max. Balken“ = {maxbars} → auf „Unbegrenzt“ stellen"})
                continue
            try:
                a = daten.ziehen(ro, name, tf, start, ende, db_pfad, holdout_ab=konf.holdout[0], holdout_frei=holdout_frei,
                                 maxbars=maxbars, d1_erster=erster if tf != "D1" else None)
            except BrokerFehler as exc:
                out.append({"symbol": sym, "tf": tf, "anzahl": 0, "status": "FEHLER", "hinweis": str(exc)[:160]})
                continue
            if tf == "D1" and a.anzahl:
                erster = int(dt.datetime.strptime(a.erster, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())
            status = a.status
            if tf == "H1" and status == "OK" and daten.jahre(a) < 6 and not holdout_frei:
                status = "ZU_KURZ"
            if tf in konf.zeitrahmen:
                out.append({"symbol": sym, "tf": tf, "anzahl": a.anzahl, "erster": a.erster, "letzter": a.letzter,
                            "sha256": a.sha256[:16], "status": status, "jahre": round(daten.jahre(a), 1)})
    return out


def konto_registrieren(terminal) -> str:
    terminal.verbinden()
    abdruck = live_guard.konto_registrieren(terminal, paths.kit_home() / "freigaben")
    return abdruck[:8] + "…"


def probe_einzel(terminal, konf: Konfiguration, *, symbol: str | None = None, warte: Callable[[float], None] = time.sleep,
                 schutz_frist_s: float = 30.0) -> dict:
    """Ein Demo-Trade mit kleinstem Volumen: eröffnen (SL+TP im Auftrag) → SL enger → per Ticket schließen. Nur DEMO, nur ohne
    Sperre (läuft über den Takt der Probe-Ablage: Journal, Sperren, Abgleich)."""
    from kit.run.loop import Bot
    sym = konf.broker_name(symbol or konf.probe_symbole[0])
    pruefung, ablage = _bot_umgebung(terminal, konf, "probe", schlaf=warte, symbol=sym)   # misst Serverversatz (Ticks laufen)
    with Schreibsperre(paths.kit_home() / "schreiber"), Schreibsperre(ablage):
        bot = Bot(terminal, ablage, konf, modus="probe", demo_pruefung=pruefung)
        vor = bot.journal._seq
        try:
            bot.starten()
            return _einzelprobe(bot, terminal, konf, sym, warte, schutz_frist_s)
        finally:
            _ende_falls_gestartet(bot.journal, vor, "EINZELPROBE", "Einzelprobe beendet")


def _einzelprobe(bot, terminal, konf: Konfiguration, sym: str, warte: Callable[[float], None], schutz_frist_s: float) -> dict:
    gesperrt = bot.einstieg_gesperrt(terminal.zeit())
    if gesperrt:
        raise live_guard.LiveGesperrt(f"Probe nicht erlaubt: {gesperrt}")
    lz = bot.lz
    spec, q = terminal.symbol(sym), terminal.quote(sym)
    if spec.trade_mode != "FULL" or not -2.0 <= terminal.zeit() - q.time_msc / 1000 <= konf.kursalter_s:
        raise live_guard.LiveGesperrt(f"Probe nicht erlaubt: Markt für {sym} nicht offen (Handelsmodus {spec.trade_mode}, "
                                      f"Kursalter {terminal.zeit() - q.time_msc / 1000:.0f} s)")
    abstand = spec.point * max(spec.stops_level + 50, 300)
    sl = rounding.sl_runden(q.ask - abstand, Side.BUY, spec)
    tp = rounding.tp_runden(q.ask + abstand, Side.BUY, spec)
    jetzt = int(terminal.zeit())
    cid = ids.client_id("PROBE-EINZEL", sym, jetzt, "ENTRY")
    t0 = time.monotonic()
    op = lz.ausfuehren(Absicht(f"PE-{jetzt}", Action.ENTRY_DEAL, sym, Side.BUY, spec.volume_min, Namensraum.PROBE, sl, tp), cid)
    bericht: dict = {"symbol": sym, "versatz_stunden": (getattr(terminal, "versatz_s", 0) or 0) / 3600,
                     "uhr_rest_s": round(getattr(terminal, "rest_s", 0.0), 2),
                     "eroeffnen": {"status": str(op.status), "retcodes": op.retcodes, "grund": op.grund,
                                   "dauer_ms": int((time.monotonic() - t0) * 1000), "ergebnis_mit_deal": bool(op.deals),
                                   "ergebnis_mit_order": bool(op.order), "gefuellt": str(op.gefuellt)}}
    if op.status is not OpStatus.ERLEDIGT:
        return bericht
    pos = None
    for _ in range(int(schutz_frist_s)):
        pos = next((p for p in terminal.positions() if p.magic == op.magic or (op.order and p.ticket == op.order)), None)
        if pos is not None:
            break
        warte(1.0)
    bericht["eroeffnen"].update({"position_gefunden": pos is not None, "magic_erhalten": bool(pos and pos.magic == op.magic),
                                 "kommentar_erhalten": bool(pos and pos.comment == ids.kommentar(op.op_id)),
                                 "kommentar_laenge": len(pos.comment) if pos else 0,
                                 "sl_auf_server": bool(pos and pos.sl == sl), "tp_auf_server": bool(pos and pos.tp == tp)})
    if pos is None or pos.magic != op.magic:
        return bericht                               # fremd wirkender magic: nicht anfassen, Server-SL/TP schützen
    neu_sl = rounding.sl_runden(sl + spec.point * 100, Side.BUY, spec)
    op2 = lz.ausfuehren(Absicht(f"PE-{jetzt}-SL", Action.PROTECT_SLTP, sym, Side.BUY, pos.volume, Namensraum.PROBE, neu_sl, tp,
                                pos.ticket), ids.client_id("PROBE-EINZEL", sym, jetzt, "SLTP"))
    lz.klaeren()
    pos2 = next((p for p in terminal.positions() if p.ticket == pos.ticket), None)
    bericht["sl_enger"] = {"status": str(op2.status), "retcodes": op2.retcodes, "sl_auf_server": bool(pos2 and pos2.sl == neu_sl)}
    op3 = bot.abbauen(pos.ticket, sym, Side.BUY, pos.volume, Namensraum.PROBE, "PROBE_EINZEL")
    lz.klaeren()
    bericht["schliessen"] = {"status": str(op3.status) if op3 else "WARTET", "retcodes": op3.retcodes if op3 else [],
                             "flach": not any(p.ticket == pos.ticket for p in terminal.positions())}
    assert bot.abgleich is not None
    b = bot.abgleich.laufen()
    bericht["abgleich"] = {"differenzen": b.differenzen, "fremde": len(b.fremde), "aktionen": len(b.aktionen)}
    magics = {op.magic} | ({op3.magic} if op3 else set())
    deals = [d for d in terminal.deals(jetzt - 600, int(terminal.zeit()) + 60) if d.magic in magics]
    bericht["deal_gruende"] = sorted({d.reason for d in deals})
    bericht["deals"] = [{"entry": d.entry, "reason": d.reason, "magic_gleich_op": d.magic in magics,
                         "position_id_gleich_ticket": d.position_id == pos.ticket} for d in deals]
    bericht["gebuehren"] = str(sum((d.commission + d.fee for d in deals), Decimal(0)))
    return bericht


VERSATZ_VERSUCHE = (300, 50)                             # erstes Symbol bis 30 s, jedes weitere bis 5 s (gesamt ≤ 60 s bei 7)


def _versatz_messen(terminal, konf: Konfiguration, schlaf: Callable[[float], None], symbol: str | None) -> None:
    """Ruhiger Markt: steht der Kursstrom des ersten Symbols, nacheinander die übrigen Probe-Symbole versuchen. Jeder andere
    Fehler (z. B. keine Ganzstundenzone) gilt sofort; scheitern alle, nennt die Meldung jede Ursache."""
    from kit.broker.seam import BrokerFehler
    kandidaten = list(dict.fromkeys([symbol or konf.broker_name(konf.probe_symbole[0])]
                                    + [konf.broker_name(s) for s in konf.probe_symbole]))
    ursachen: list[str] = []
    for i, kandidat in enumerate(kandidaten):
        try:
            terminal.messe_versatz(kandidat, schlaf=schlaf, versuche=VERSATZ_VERSUCHE[min(i, 1)])
            return
        except BrokerFehler as exc:
            if "Kursstrom steht" not in str(exc):
                raise
            ursachen.append(str(exc))
    raise BrokerFehler("Serverversatz nicht messbar – " + " | ".join(ursachen))


def _ende_falls_gestartet(journal, vor: int, code: str, text: str) -> None:
    """ENDE nur, wenn dieser Lauf einen START geschrieben und noch kein ENDE hat – sonst meldete der Status „läuft“ für einen
    Prozess, der längst weg ist."""
    from kit.state.journal import Journal
    frisch = Journal(journal.ordner, uhr=journal.uhr, fsync=journal.fsync)   # Stand von der Platte: Strg+C kann mitten in
    neu = [s for s in frisch.lesen() if s["seq"] > vor]                        # einem Schreibvorgang gekommen sein
    if any(s["art"] == "START" for s in neu) and not any(s["art"] == "ENDE" for s in neu):
        frisch.schreiben("ENDE", code, text)


def _bot_umgebung(terminal, konf: Konfiguration, modus: str, *, versatz_messen: bool = True,
                  schlaf: Callable[[float], None] = time.sleep, symbol: str | None = None):
    """Verbinden, Serverversatz messen (Ticks müssen laufen), Demo-Prüfung (Allowlist, Algo Trading) – sonst kein Start."""
    if modus == "live":
        live_guard.live_pruefen()
    umzug.pruefen()                                # nie auf einer leeren neuen Ablage starten, solange Altbestand offen ist
    terminal.verbinden()
    if versatz_messen:
        _versatz_messen(terminal, konf, schlaf, symbol)
    pruefung = live_guard.demo_pruefung(terminal, paths.kit_home() / "freigaben")
    grund = pruefung()
    if grund:
        raise live_guard.LiveGesperrt(f"Probe nicht erlaubt: {grund}" if modus == "probe" else f"Start verweigert: {grund}")
    ablage = paths.ablage(modus)
    ablage.mkdir(parents=True, exist_ok=True)
    return pruefung, ablage


def lauf(terminal, konf: Konfiguration, modus: str, *, dauer_min: float | None = None) -> int:
    """Takt im Modus probe (Technik-Messung T-DAUER) bzw. demo (Demo-Live, erst nach F-06/F-07). Exit-Code des Takts.
    Ein schreibender Bot je Windows-Benutzer (globale Schreibsperre) und je Ablage."""
    from kit.run.loop import Bot, Ende
    if modus == "demo":
        raise live_guard.LiveGesperrt("Demo-Live startet erst nach bestandenem 85-%-Tor (F-06/F-07) – noch keine Strategie freigegeben.")
    pruefung, ablage = _bot_umgebung(terminal, konf, modus)
    (ablage / "BEENDEN").unlink(missing_ok=True)
    with Schreibsperre(paths.kit_home() / "schreiber"), Schreibsperre(ablage):
        bot = Bot(terminal, ablage, konf, modus=modus, probe=modus == "probe", demo_pruefung=pruefung, versatz_takt_s=3600.0)
        vor = bot.journal._seq
        try:
            bot.starten()
        except Ende as e:
            _ende_falls_gestartet(bot.journal, vor, e.grund, f"Start abgebrochen: {e.grund}")
            return e.code
        except BaseException as exc:                     # auch Strg+C im Bot-Fenster
            _ende_falls_gestartet(bot.journal, vor, "STARTFEHLER", f"Start abgebrochen: {type(exc).__name__}")
            raise
        try:
            return bot.laufen(bis=terminal.zeit() + dauer_min * 60 if dauer_min else None)
        except BaseException as exc:                     # laufen schreibt ENDE selbst – außer bei Strg+C und unerwarteten Fehlern
            _ende_falls_gestartet(bot.journal, vor, "ABBRUCH" if isinstance(exc, KeyboardInterrupt) else "PROGRAMMFEHLER",
                                  f"Takt beendet: {type(exc).__name__}")
            raise


def skripte(terminal, konf: Konfiguration, *, symbol: str | None = None, nur: list[str] | None = None, wiederholen: int = 1) -> list[dict]:
    """D-Skripte/Killer-Tests auf DEMO (beaufsichtigt, F-03b). Nur ohne aktive Sperre. Ergebnisse redigiert."""
    from kit.probe.skripte import Skripte
    from kit.report.redact import redigieren
    from kit.run.loop import Bot
    pruefung, ablage = _bot_umgebung(terminal, konf, "probe")
    aus: list[dict] = []
    with Schreibsperre(paths.kit_home() / "schreiber"), Schreibsperre(ablage):
        bot = Bot(terminal, ablage, konf, modus="probe", demo_pruefung=pruefung)
        vor = bot.journal._seq
        try:
            bot.starten()
            for _ in range(max(1, wiederholen)):
                for e in Skripte(bot, symbol or konf.probe_symbole[0]).alle(nur):
                    aus.append({"skript": e.skript, "urteil": e.urteil, "kt": e.kt, "grund": e.grund,
                                "schritte": [{"schritt": s.schritt, "soll": s.soll, "ist": s.ist, "ok": s.ok} for s in e.schritte]})
        finally:
            _ende_falls_gestartet(bot.journal, vor, "SKRIPTE", "Skriptlauf beendet")
    return redigieren(aus)


def export_schreiben(name: str, daten_: object) -> Path:
    ordner = paths.kit_home() / "export"
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"{name}-{dt.datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    pfad.write_text(json.dumps(daten_, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return pfad
