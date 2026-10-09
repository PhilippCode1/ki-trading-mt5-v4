"""MT5-Adapter über die vom SIM getriebene MetaTrader5-Attrappe: Abbildung, Zeitdrehung, fail-closed, Nur-Lesen, Demo-Wächter."""
from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest

from kit import betrieb, live_guard, paths
from kit.broker.mt5_real import Mt5Terminal
from kit.broker.seam import BrokerFehler
from kit.broker.sim import SimTerminal, Uhr
from kit.broker.sim_modul import SimMt5Modul
from kit.config import Konfiguration
from kit.domain.types import Absicht, Action, Bar, HandelsModus, KontoModus, Namensraum, OpStatus, Side
from kit.orders.lifecycle import Lebenszyklus
from kit.research import daten
from kit.state.journal import Journal
from kit_tests.hilfen import eurusd

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
VERSATZ = 3 * 3600


def _paar(modus=KontoModus.HEDGING, handelsmodus=HandelsModus.DEMO):
    uhr = Uhr()
    sim = SimTerminal([eurusd(), eurusd("GBPUSD"), eurusd("USDJPY")], modus=modus, handelsmodus=handelsmodus, uhr=uhr)
    for s in ("EURUSD", "GBPUSD", "USDJPY"):
        sim.setze_kurs(s, "1.10500", "1.10502")
    modul = SimMt5Modul(sim, versatz_s=VERSATZ)
    term = Mt5Terminal(modul, versatz_s=VERSATZ, schluessel_ordner=paths.kit_home() / "geheim", uhr=uhr, prozess_pruefen=lambda: True)
    term.verbinden()
    return sim, modul, term, uhr


def _konf() -> Konfiguration:
    return Konfiguration("", ("EURUSD", "GBPUSD", "USDJPY"), ("EURUSD",))


def test_abbildung_konto_symbol_kurs():
    sim, modul, term, uhr = _paar()
    a = term.account()
    assert a.trade_mode is HandelsModus.DEMO and a.margin_mode is KontoModus.HEDGING and a.abdruck and a.trade_allowed
    s = term.symbol("EURUSD")
    assert s.filling == "IOC" and s.tick_size == D("0.00001") and s.volume_step == D("0.01")
    q = term.quote("EURUSD")
    assert q.bid == D("1.105") and abs(q.time_msc / 1000 - uhr()) < 1           # Serverzeit zurück nach UTC gedreht


def test_lebenszyklus_ueber_echten_adaptercode(tmp_path):
    sim, modul, term, uhr = _paar()
    lz = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit))
    a = Absicht("I1", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.STRATEGIE, D("1.10000"), D("1.11000"))
    op = lz.ausfuehren(a, "c1")
    assert op.status is OpStatus.ERLEDIGT and modul.aufrufe["order_send"] == 1
    p = term.positions()[0]
    assert p.magic == op.magic and p.sl == D("1.10000") and abs(p.time - uhr()) < 2
    deals = term.deals(int(uhr()) - 60, int(uhr()) + 60)
    assert [d.reason for d in deals] == ["EXPERT"] and deals[0].entry == "IN"
    r = Absicht("R", Action.REDUCE_DEAL, "EURUSD", Side.SELL, D("0.10"), Namensraum.STRATEGIE, ticket=p.ticket)
    assert lz.ausfuehren(r, "r1").status is OpStatus.ERLEDIGT and term.positions() == []


def test_real_konto_null_sendungen_auf_allen_pfaden(tmp_path):
    sim, modul, term, uhr = _paar(handelsmodus=HandelsModus.REAL)
    lz = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit))
    for aktion, seite in ((Action.ENTRY_DEAL, Side.BUY), (Action.REDUCE_DEAL, Side.SELL), (Action.PROTECT_SLTP, Side.BUY)):
        a = Absicht(f"A-{aktion}", aktion, "EURUSD", seite, D("0.10"), Namensraum.PROBE, D("1.10000"), ticket=1)
        assert lz.ausfuehren(a, f"x-{aktion}").grund == "NICHT_DEMO"
    assert modul.aufrufe.get("order_send", 0) == 0 and modul.aufrufe.get("order_check", 0) == 0
    with pytest.raises(live_guard.LiveGesperrt):
        live_guard.live_pruefen()


def test_initialize_nie_mit_zugangsdaten_und_mt5_nur_im_adapter():
    quelle = (ROOT / "kit" / "broker" / "mt5_real.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call) and getattr(knoten.func, "attr", "") == "initialize":
            assert {k.arg for k in knoten.keywords} <= {"path"}
        if isinstance(knoten, (ast.Import, ast.ImportFrom)):
            namen = [n.name for n in knoten.names] if isinstance(knoten, ast.Import) else [knoten.module or ""]
            assert "MetaTrader5" not in namen                     # nur verzögert über importlib
    assert "mt5.login(" not in quelle


def test_kein_terminal_kein_start():
    sim = SimTerminal([eurusd()])
    term = Mt5Terminal(SimMt5Modul(sim), prozess_pruefen=lambda: False)
    with pytest.raises(BrokerFehler):
        term.verbinden()


def test_none_antworten_sind_fehler():
    sim, modul, term, uhr = _paar()
    modul.positions_get = lambda: None
    with pytest.raises(BrokerFehler):
        term.positions()
    modul.copy_rates_range = lambda *a: None
    with pytest.raises(BrokerFehler):
        term.bars("EURUSD", "D1", 0, int(uhr()))
    modul.history_deals_get = lambda *a: None
    with pytest.raises(BrokerFehler):
        term.deals(0, int(uhr()))


def test_kerzen_mit_zeitdrehung_und_abgeschlossen_markiert():
    sim, modul, term, uhr = _paar()
    t0 = int(uhr()) - 3 * 86400
    for i in range(3):
        sim.kerze(Bar("EURUSD", t0 + i * 86400, D("1.1"), D("1.11"), D("1.09"), D("1.105")))
    sim.kerze(Bar("EURUSD", int(uhr()) - 3600, D("1.1"), D("1.11"), D("1.09"), D("1.105")))
    bars = term.bars("EURUSD", "D1", t0 - 10, int(uhr()) + 10)
    assert [b.time for b in bars][:3] == [t0, t0 + 86400, t0 + 2 * 86400]
    assert all(b.is_closed for b in bars[:3]) and not bars[-1].is_closed


def test_versatz_messung():
    sim, modul, term, uhr = _paar()
    term.versatz_s = None
    assert term.messe_versatz("EURUSD", schlaf=lambda s: uhr.vor(s)) == VERSATZ
    with pytest.raises(BrokerFehler):
        term.messe_versatz("EURUSD", schlaf=lambda s: None)     # Kursstrom steht


def test_rauchtest_nur_lesend_und_redigiert():
    sim, modul, term, uhr = _paar()
    erg = betrieb.rauchtest(term, _konf(), versatz_messen=False)
    assert modul.aufrufe.get("order_send", 0) == 0 and modul.aufrufe.get("order_check", 0) == 0
    text = json.dumps(erg)
    assert str(modul.login) not in text and modul.server not in text and "Probe" not in text and "balance" not in text
    assert erg["konto"]["handelsmodus"] == "DEMO" and erg["symbole"]["EURUSD"]["fuellart"] == "IOC"


def test_konto_registrieren_nur_demo():
    sim, modul, term, uhr = _paar(handelsmodus=HandelsModus.REAL)
    with pytest.raises(live_guard.LiveGesperrt):
        betrieb.konto_registrieren(term)
    sim.handelsmodus = HandelsModus.DEMO
    betrieb.konto_registrieren(term)
    assert term.account().abdruck in live_guard.allowlist_laden(paths.kit_home() / "freigaben")


def test_einzelprobe_kompletter_zyklus_nur_mit_registrierung():
    sim, modul, term, uhr = _paar()
    with pytest.raises(live_guard.LiveGesperrt):
        betrieb.probe_einzel(term, _konf(), warte=uhr.vor)
    betrieb.konto_registrieren(term)
    b = betrieb.probe_einzel(term, _konf(), warte=uhr.vor)
    assert b["eroeffnen"]["status"] == "ERLEDIGT" and b["eroeffnen"]["sl_auf_server"] and b["eroeffnen"]["magic_erhalten"]
    assert b["sl_enger"]["sl_auf_server"] and b["schliessen"]["flach"] and b["abgleich"]["differenzen"] == []
    assert b["deal_gruende"] == ["EXPERT"] and b["versatz_stunden"] == 3
    assert {(d["entry"], d["magic_gleich_op"], d["position_id_gleich_ticket"]) for d in b["deals"]} == {("IN", True, True),
                                                                                                    ("OUT", True, True)}


def test_datenabzug_hash_und_holdout_sperre(tmp_path):
    sim, modul, term, uhr = _paar()
    with pytest.raises(RuntimeError, match="Serverzeit"):            # gemessener Versatz würde die Zeitbasis mischen (F-04)
        daten.ziehen(term, "EURUSD", "D1", "2010-01-01", "2010-01-31", tmp_path / "e.sqlite", holdout_ab="2021-07-01")
    term.versatz_s = None                                          # wie kit daten-ziehen: Versatz nicht gemessen → Serverzeit
    for i in range(5):
        sim.kerze(Bar("EURUSD", 1262304000 + i * 86400, D("1.4"), D("1.41"), D("1.39"), D("1.405")))   # ab 01.01.2010
    a = daten.ziehen(term, "EURUSD", "D1", "2010-01-01", "2010-01-31", tmp_path / "e.sqlite", holdout_ab="2021-07-01")
    assert a.status == "OK" and a.anzahl == 5 and len(a.sha256) == 64
    with pytest.raises(daten.HoldoutGesperrt):
        daten.ziehen(term, "EURUSD", "D1", "2021-01-01", "2021-12-31", tmp_path / "e.sqlite", holdout_ab="2021-07-01")
    leer = daten.ziehen(term, "GBPUSD", "D1", "2010-01-01", "2010-01-31", tmp_path / "e.sqlite", holdout_ab="2021-07-01")
    assert leer.status == "LEER"


def test_konfiguration_verbietet_zugangsdaten(tmp_path):
    from kit import config
    p = tmp_path / "k.toml"
    p.write_text('[terminal]\npfad = ""\nlog' + 'in = 1\n[symbole]\nstrategie=["EURUSD"]\nprobe=["EURUSD"]\n', encoding="utf-8")
    with pytest.raises(ValueError):
        config.laden(p)
    assert config.laden().strategie_symbole[0] == "EURUSD"


def test_cli_probe_ohne_schreiben_sendet_nichts(capsys, monkeypatch):
    from kit import cli
    monkeypatch.setattr(cli, "_terminal", lambda konf: pytest.fail("keine Verbindung ohne --schreiben"))
    assert cli.main(["probe", "einzel"]) == 2                   # Abbruch vor jeder Verbindung und Sendung
    assert "Ohne --schreiben" in capsys.readouterr().out


def test_cli_anmeldefehler_klare_meldung_und_trennen(capsys, monkeypatch):
    from kit import cli

    class Abgelehnt:
        getrennt = False

        def verbinden(self):
            raise BrokerFehler("initialize fehlgeschlagen: (-6, 'Terminal: Authorization failed')")

        def trennen(self):
            Abgelehnt.getrennt = True

    monkeypatch.setattr(cli, "_terminal", lambda konf: Abgelehnt())
    assert cli.main(["rauchtest"]) == 4
    out = capsys.readouterr().out
    assert "DEMO-Konto anmelden" in out and "Traceback" not in out and Abgelehnt.getrennt


def test_datenabzug_maxbars_fehler_je_zeile_und_nur_fehlende(tmp_path):
    from kit.config import Konfiguration
    sim, modul, term, uhr = _paar()
    term.versatz_s = None                                          # wie kit daten-ziehen: Abzug in Serverzeit (F-04)
    for s in ("EURUSD", "GBPUSD"):
        for i in range(5):
            sim.kerze(Bar(s, 1262304000 + i * 86400, D("1.4"), D("1.41"), D("1.39"), D("1.405")))
    konf = Konfiguration("", ("EURUSD", "GBPUSD"), ("EURUSD",), entwicklung=("2010-01-01", "2010-01-31"), zeitrahmen=("D1", "H1"))
    modul.terminal_info = lambda: __import__("types").SimpleNamespace(**{**vars(SimMt5Modul.terminal_info(modul)), "maxbars": 20000})
    echt = modul.copy_rates_range
    modul.copy_rates_range = lambda s, tf, a, b: None if s == "GBPUSD" else echt(s, tf, a, b)
    erg = betrieb.daten_ziehen(term, konf, tmp_path / "e.sqlite")
    status = {(z["symbol"], z["tf"]): z["status"] for z in erg}
    assert status == {("EURUSD", "D1"): "OK", ("EURUSD", "H1"): "MAXBARS_ZU_KLEIN", ("GBPUSD", "D1"): "FEHLER",
                      ("GBPUSD", "H1"): "MAXBARS_ZU_KLEIN"}                    # ein Fehler betrifft nur seine Zeile
    modul.copy_rates_range = echt
    erg2 = betrieb.daten_ziehen(term, konf, tmp_path / "e.sqlite", nur_fehlende=True)
    status2 = {(z["symbol"], z["tf"]): z["status"] for z in erg2}
    assert status2[("EURUSD", "D1")] == "VORHANDEN" and status2[("GBPUSD", "D1")] == "OK"
