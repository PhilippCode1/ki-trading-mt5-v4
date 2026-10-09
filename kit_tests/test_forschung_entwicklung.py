"""Ende-zu-Ende der Entwicklungsauswertung F-04 auf einer synthetischen Datenbank: Vorregistrierung → Kostenprofil (Datensicht) →
Läufe (Hauptprofil, Kosten × 1,5, Kommission 3,25) → Bewertung, Parität, Zufallsbasis, DSR → Bericht → Versuchsprotokoll verifiziert.
Privat: braucht config/kostenprofil/f04_startwerte.json (nicht im Spiegel)."""
from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from kit.research import daten, entwicklung, protokoll, trials
from kit_tests import backtest_hilfen as bh

pytestmark = pytest.mark.privat
START = int(dt.datetime(2012, 11, 4, 21, 0, tzinfo=dt.UTC).timestamp())     # So 21:00 UTC = Mo 00:00 Serverzeit
NUR = ("S-REV-01-k2.0-z0.50-r2", "S-REV-02-L20-z0.5", "S-BL-01")


def _vorab(log) -> None:
    for familie in protokoll.FAMILIEN:
        protokoll.anhaengen({"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": "2026-10-08", "family": familie, "lauf": "TEST",
                             "prereg_sha": protokoll.PREREG_SHA, "commit": "0" * 40, "code": {}}, log)


def test_auswertung_ende_zu_ende(tmp_path):
    db = tmp_path / "entwicklung.sqlite"
    bh.synthetische_db(db, start=START, wochen=17, saat=2, sigma=0.0022)
    log = tmp_path / "versuchsprotokoll.jsonl"
    spread = tmp_path / "spreadprofil.json"
    with pytest.raises(protokoll.ProtokollFehler):                                           # ohne Vorregistrierung: nein
        entwicklung.kostenprofil_eintragen(datum="2026-10-08", db=db, protokoll_pfad=log, spread_pfad=spread, vorpruefen=False)
    with pytest.raises(protokoll.ProtokollFehler):                                           # Vorprüfung: Code nicht signiert
        entwicklung.kostenprofil_eintragen(datum="2026-10-08", db=db, protokoll_pfad=log, spread_pfad=spread)
    _vorab(log)
    k = entwicklung.kostenprofil_eintragen(datum="2026-10-08", db=db, protokoll_pfad=log, spread_pfad=spread, vorpruefen=False)
    assert k["abzuege"] == 21 and k["verworfen_holdout"] == 0 and spread.is_file()
    with pytest.raises(protokoll.ProtokollFehler, match="schon"):
        entwicklung.kostenprofil_eintragen(datum="2026-10-08", db=db, protokoll_pfad=log, spread_pfad=spread, vorpruefen=False)
    with pytest.raises(protokoll.ProtokollFehler):                                           # Vorprüfung vor der Auswertung
        entwicklung.ausfuehren(datum="2026-10-08", db=db, protokoll_pfad=log, spread_pfad=spread, bericht_ordner=tmp_path, nur=NUR)
    erg = entwicklung.ausfuehren(datum="2026-10-08", prozesse=3, db=db, protokoll_pfad=log, spread_pfad=spread, bericht_ordner=tmp_path,
                                 melden=lambda *_: None, nur=NUR, vorpruefen=False)
    b = json.loads((tmp_path / "2026-10-08_entwicklung.json").read_text(encoding="utf-8"))
    md = (tmp_path / "2026-10-08_entwicklung.md").read_text(encoding="utf-8")
    assert [v["id"] for v in b["varianten"]] == list(NUR[:2]) and b["referenz_s_bl_01"]["variante"] == "S-BL-01"
    for v in b["varianten"]:
        h = v["haupt"]
        assert h["technik_ok"] and h["paritaet"]["signale"]["quote"] == 1.0 and h["paritaet"]["trades"]["quote"] == 1.0
        assert h["bewertung"]["kriterien"]["technik"]["ok"] is True and h["einstieg_nachteil_ticks"]["anteil_ungleich_null"] == 0
        assert h["bewertung"]["kennzahlen"]["n"] > 0 and set(h["bewertung"]["kriterien"]) >= {"quote", "zufallsbasis", "band_budget"}
        assert h["oos"]["von"] == int(dt.datetime(2013, 1, 1, tzinfo=dt.UTC).timestamp())       # Anpassung 2010–2012 zählt nicht
        assert v["kosten_x1_5"]["trades"] > 0 and v["gegenprobe_3_25"]["trades"] > 0
    assert "Grenzen dieser Auswertung" in md and "Keine Anlageberatung" in md
    text = json.dumps(b) + json.dumps(protokoll.lesen(log))
    swaps = {w for paar in entwicklung.startwerte()["swap_punkte"].values() for w in paar}
    assert not any(re.search(rf"(?<![\d.]){re.escape(w)}(?!\d)", text) for w in swaps)       # Swappunkte bleiben privat
    assert "swap_punkte\": {" not in json.dumps(b)
    assert "median" not in json.dumps(b) and "median" not in json.dumps(protokoll.lesen(log))   # Spreadprofil bleibt privat
    eintraege = protokoll.lesen(log)
    assert trials.verify(eintraege) == []
    assert trials.trial_count(eintraege, "F04-ZIEL-STOP") == 2 and trials.trial_count(eintraege, "F04-REFERENZ") == 1
    assert [e["body"].get("phase") for e in eintraege if e["body"]["kind"] == "TRIAL"] == ["BEGINN"] * 3 + ["ERGEBNIS"] * 3
    assert erg["auswahl"] in (None, *NUR)
    with pytest.raises(protokoll.ProtokollFehler, match="schon ausgewertet"):               # genau eine Auswertung je Familie
        entwicklung.ausfuehren(datum="2026-10-09", db=db, protokoll_pfad=log, spread_pfad=spread, bericht_ordner=tmp_path, nur=NUR,
                               vorpruefen=False)
    assert protokoll.vollstaendigkeit(log, lauf="TEST", varianten_ids=NUR) == []


def test_datenleser_prueft_hash_und_holdout(tmp_path):
    db = tmp_path / "e.sqlite"
    bh.synthetische_db(db, start=START, wochen=2)
    bars, info = daten.lesen(db, "EURUSD", "H1", start="2010-01-01", ende="2021-06-30", holdout_ab="2021-07-01", versatz_s=bh.VERSATZ)
    assert info["anzahl"] == len(bars) > 0
    roh, _ = daten.lesen(db, "EURUSD", "H1", start="2010-01-01", ende="2021-06-30", holdout_ab="2021-07-01")
    assert [b.time - bh.VERSATZ for b in roh] == [b.time for b in bars]                     # gespeichert Serverzeit, zurück UTC
    assert (roh[0].time // 3600) % 24 == 0                                                   # Wochenöffnung Mo 00:00 Serverzeit
    with pytest.raises(daten.HoldoutGesperrt):
        daten.lesen(db, "EURUSD", "H1", start="2010-01-01", ende="2021-06-30", holdout_ab="2012-11-10")
    import sqlite3
    con = sqlite3.connect(db)
    with con:
        con.execute("UPDATE kerze SET c = '9.99999' WHERE rowid = (SELECT MIN(rowid) FROM kerze)")
    con.close()
    with pytest.raises(daten.DatenFehler):
        daten.lesen(db, "EURUSD", "H1", start="2010-01-01", ende="2021-06-30", holdout_ab="2021-07-01")
    with pytest.raises(daten.DatenFehler):
        daten.lesen(db, "EURUSD", "M5", start="2010-01-01", ende="2021-06-30", holdout_ab="2021-07-01")


def test_datenleser_verwirft_kerzen_ueber_die_holdout_grenze(tmp_path):
    """Review F-04: D1/H4 beginnen auf Servergrenzen (21:00 UTC). Eine Kerze, die vor dem Holdout beginnt, aber erst danach endet, enthält
    Holdout-Kurse und wird nie zurückgegeben; der Abzug bleibt über alle Kerzen hashgeprüft."""
    db = tmp_path / "e.sqlite"
    h1 = bh.synthetische_db(db, start=START, wochen=2)
    letzte_d1 = bh.verdichten(h1["EURUSD"], 86400)[-1]
    grenze = dt.datetime.fromtimestamp(letzte_d1.time + 6 * 3600, dt.UTC).date().isoformat()   # Tagesgrenze UTC mitten in der Kerze
    d1, info = daten.lesen(db, "EURUSD", "D1", start="2010-01-01", ende="2021-06-30", holdout_ab=grenze, versatz_s=bh.VERSATZ)
    assert info["verworfen_holdout"] == 1 and d1[-1].time < letzte_d1.time
    assert all(b.time + 86400 <= int(dt.datetime.fromisoformat(grenze).replace(tzinfo=dt.UTC).timestamp()) for b in d1)
    with pytest.raises(daten.HoldoutGesperrt):                    # H1-Kerzen, die nach der Grenze beginnen: Abbruch statt Verwerfen
        daten.lesen(db, "EURUSD", "H1", start="2010-01-01", ende="2021-06-30", holdout_ab=grenze, versatz_s=bh.VERSATZ)



def test_abzug_verweigert_gemessenen_versatz(tmp_path):
    """Die Abzüge stehen in Serverzeit; ein Terminal mit gemessenem Versatz würde UTC-Zeiten dazumischen (fail-closed)."""
    class Terminal:
        versatz_s = 10800.0

        def bars(self, *a):
            raise AssertionError("darf nicht gelesen werden")
    with pytest.raises(RuntimeError, match="Serverzeit"):
        daten.ziehen(Terminal(), "EURUSD", "H1", "2010-01-01", "2010-01-31", tmp_path / "x.sqlite", holdout_ab="2021-07-01")
