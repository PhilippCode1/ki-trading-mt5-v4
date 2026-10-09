"""Ende-zu-Ende der Runde 2 (F-05) auf einer synthetischen Datenbank, ohne scikit-learn (Training durch eine feste Attrappe ersetzt):
Vorregistrierung → Datensicht F05-DATEN (Datensätze, nur Hashes im Protokoll) → je Variante BEGINN → Modelle (nie überschreiben) →
Takt mit der Hülle in drei Kostenprofilen → Parität (Signal, Trade, Datensatz ↔ Takt) → Bericht → ERGEBNIS; zweite Auswertung verweigert.
Mit scikit-learn läuft dieselbe Kette in test_meta_sklearn.py nicht noch einmal (Laufzeit); das echte Training prüft dort die Parität.
Privat: braucht config/kostenprofil/f04_startwerte.json (nicht im Spiegel)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

import pytest

from kit.research import entwicklung, meta, protokoll, trials
from kit.strategy import meta_filter as mf
from kit_tests import backtest_hilfen as bh

pytestmark = pytest.mark.privat
START = int(dt.datetime(2012, 5, 6, 21, 0, tzinfo=dt.UTC).timestamp())          # So 21:00 UTC = Mo 00:00 Serverzeit
NUR = ("F05-REV01-LOGREG", "F05-REV02-HGB")


def utc(*a) -> int:
    return int(dt.datetime(*a, tzinfo=dt.UTC).timestamp())


def _plan() -> list[dict]:
    aus = []
    for von, bis in ((utc(2013, 1, 1), utc(2013, 1, 22)), (utc(2013, 1, 22), utc(2013, 2, 12)), (utc(2013, 2, 12), None)):
        aus.append({"test_von": von, "test_bis": bis, "embargo_bis": meta.embargo_ende(von), "fit_von": von - 12 * 7 * 86400,
                    "val_von": von - 4 * 7 * 86400, "holdout": bis is None})
    return aus


def attrappe(zeilen, v, plan) -> dict:
    """Festes Modell je Fenster (keine Anpassung): p hängt an allen Merkmalen (jede Abweichung zwischen Datensatz und Takt kippt
    Entscheidungen); Trainingsgrenzen und Mengenangaben wie beim echten Training (forschung/meta_training.py)."""
    namen = mf.merkmal_namen(v.art)
    basis = meta.basis_strategie(v.basis_id)

    def grenzen(zs):
        return {"n": len(zs), "min_t_ent": min((z["t_ent"] for z in zs), default=None), "max_t_ent": max((z["t_ent"] for z in zs), default=None),
                "max_t_exit": max((z["t_exit"] for z in zs), default=None)}

    def fenster(f):
        innen = meta.menge(zeilen, f["fit_von"], f["val_von"])
        final, val = meta.menge(zeilen, f["fit_von"], f["test_von"]), meta.menge(zeilen, f["val_von"], f["test_von"])
        koef = [(-0.6, 0.3, 40.0, -0.5, -8.0, 0.2, 0.4, -0.7, 0.3, -0.2, 0.1, -0.1, 0.2, 0.0, -0.2, 0.3, -0.3)[i] for i in range(len(namen))]
        modell = {"art": "LOGREG", "merkmale": list(namen), "mittel": [0.0] * len(namen), "skala": [1.0] * len(namen),
                  "koeffizienten": koef, "achsenabschnitt": 0.2,
                  "training": {"fit_von": f["fit_von"], "fit_bis": f["test_von"], "n": len(final),
                               "max_t_ent": max(z["t_ent"] for z in final), "max_t_exit": max(z["t_exit"] for z in final),
                               "val_von": f["val_von"], "val_max_t_exit": max((z["t_exit"] for z in val), default=0)}}
        return {**{k: f[k] for k in meta.PLAN_SCHLUESSEL}, "schwelle": 0.5, "modell": modell,
                "grenzen": {"innen": grenzen(innen), "validierung": grenzen(val), "final": grenzen(final)},
                "n_final": len(final), "n_validierung": len(val), "validierung": {"quote": 0.6, "n": len(val)}}
    alle = [fenster(f) for f in plan]
    return {"schema": "meta_filter/1", "lauf": "F-05", "variante": v.id, "basis_variante": v.basis_id, "basis_name": basis.name,
            "basis_parameter": basis.parameter(), "art": v.art, "modell_art": v.modell, "merkmale": list(namen),
            "datensatz_sha": hashlib.sha256(meta.datensatz_text(zeilen).encode("utf-8")).hexdigest(),
            "fenster": [f for f, p in zip(alle, plan, strict=True) if not p["holdout"]],
            "holdout": next(f for f, p in zip(alle, plan, strict=True) if p["holdout"]), "paritaet_max": 0.0}


def _prereg(log, familien, lauf, sha) -> None:
    for familie in familien:
        protokoll.anhaengen({"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": "2026-10-09", "family": familie, "lauf": lauf,
                             "prereg_sha": sha, "commit": "0" * 40, "code": {}}, log)


def test_runde2_ende_zu_ende(tmp_path):
    db = tmp_path / "entwicklung.sqlite"
    bh.synthetische_db(db, start=START, wochen=40, saat=3, sigma=0.0022)
    log = tmp_path / "versuchsprotokoll.jsonl"
    ds, modelle = tmp_path / "ds", tmp_path / "modelle"
    _prereg(log, protokoll.FAMILIEN, "TEST", protokoll.PREREG_SHA)
    with pytest.raises(protokoll.ProtokollFehler, match="F-05"):                                # ohne Vorregistrierung F-05
        meta.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    _prereg(log, protokoll.FAMILIEN_F05, "F-05", protokoll.PREREG_F05_SHA)
    with pytest.raises(protokoll.ProtokollFehler, match="F-04-Datensicht"):                     # nutzt genau die F-04-Abzüge
        meta.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    entwicklung.kostenprofil_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, spread_pfad=tmp_path / "sp.json", vorpruefen=False)
    with pytest.raises(protokoll.ProtokollFehler):                                               # Vorprüfung: Code nicht signiert
        meta.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds)
    ds.mkdir()
    (ds / f"{meta.BASIS_REV02}.jsonl").write_text("alt\n", encoding="utf-8")
    with pytest.raises(protokoll.ProtokollFehler, match="ohne Datensicht"):                     # Rest eines abgebrochenen Laufs
        meta.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    (ds / f"{meta.BASIS_REV02}.jsonl").unlink()
    d = meta.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    assert set(d["datensaetze"]) == set(meta.BASEN) and all(x["zeilen"] > 0 for x in d["datensaetze"].values())
    with pytest.raises(protokoll.ProtokollFehler, match="schon"):
        meta.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    sicht = [e for e in protokoll.lesen(log) if e["body"]["kind"] == "DATA_VIEW" and e["body"]["family"] == meta.FAMILIE_DATEN][-1]
    assert '"x"' not in json.dumps(sicht["body"])                                                # keine Merkmalswerte im Protokoll
    assert all(k in sicht["body"]["datensaetze"][meta.BASIS_REV01]["zaehlung"] for k in ("zeilen", "ausserhalb_fenster", "stop_zu_ziel"))
    kw = {"datum": "2026-10-09", "trainer": attrappe, "prozesse": 4, "db": db, "protokoll_pfad": log, "datensatz_ordner": ds,
          "modell_ordner": modelle, "bericht_ordner": tmp_path, "melden": lambda *_: None, "nur": NUR, "plan_werte": _plan()}
    with pytest.raises(protokoll.ProtokollFehler):                                               # Vorprüfung vor der Auswertung
        meta.ausfuehren(**kw)
    (ds / f"{meta.BASIS_REV01}.jsonl").write_text("x\n", encoding="utf-8")
    with pytest.raises(protokoll.ProtokollFehler, match="Hash der Datensicht"):                 # Datensatz an die Sicht gebunden
        meta.ausfuehren(**kw, vorpruefen=False)
    from kit.backtest.ausstieg import Markt  # Datensatz neu wie in der Datensicht
    k = entwicklung.daten_laden(db, ("H1", "H4"), meta._soll(meta._f04_sicht(protokoll.lesen(log))))["kerzen"]
    profil = entwicklung.kostenprofil("HAUPT", entwicklung.startwerte())
    basis = meta.basis_strategie(meta.BASIS_REV01)
    zeilen, _ = meta.datensatz(basis, "REV01", meta.takt_kerzen(k["H1"], k["H4"], "H1", profil),
                               Markt(k["H1"], profil, versatz_s=entwicklung.serverversatz_daten()))
    (ds / f"{meta.BASIS_REV01}.jsonl").write_text(meta.datensatz_text(zeilen), encoding="utf-8", newline="\n")
    erg = meta.ausfuehren(**kw, vorpruefen=False)
    b = json.loads((tmp_path / "2026-10-09_runde2.json").read_text(encoding="utf-8"))
    md = (tmp_path / "2026-10-09_runde2.md").read_text(encoding="utf-8")
    assert [v["id"] for v in b["varianten"]] == list(NUR) and erg["auswahl"] in (None, *NUR)
    for v in b["varianten"]:
        h = v["haupt"]
        assert h["technik_ok"] and h["paritaet"]["signale"]["quote"] == 1.0 and h["paritaet"]["trades"]["quote"] == 1.0
        assert h["bewertung"]["kriterien"]["technik"]["wert"]["datensatz_paritaet"] == 1.0
        assert v["training"]["datensatz_paritaet"]["quote"] == 1.0 and v["training"]["datensatz_paritaet"]["takt"] > 0
        assert h["bewertung"]["kriterien"]["technik"]["ok"] is True and h["bewertung"]["kennzahlen"]["n"] > 0
        f = v["training"]["filter"]
        assert f["entscheidungen"].get("EMBARGO", 0) > 0 and f["entscheidungen"].get("HANDELN", 0) > 0
        assert v["kosten_x1_5"]["trades"] > 0 and v["gegenprobe_3_25"]["trades"] > 0
    for teil in ("Filterwirkung", "Schwellen je Testfenster", "Grenzen dieser Auswertung", "Keine Anlageberatung"):
        assert teil in md
    text = json.dumps(b) + json.dumps(protokoll.lesen(log))
    swaps = {w for paar in entwicklung.startwerte()["swap_punkte"].values() for w in paar}
    assert not any(re.search(rf"(?<![\d.]){re.escape(w)}(?!\d)", text) for w in swaps)       # Swappunkte bleiben privat
    assert "median" not in json.dumps(b)                                                         # Spreadprofil bleibt privat
    eintraege = protokoll.lesen(log)
    assert trials.verify(eintraege) == [] and trials.trial_count(eintraege, meta.FAMILIE) == 2
    phasen = [e["body"].get("phase") for e in eintraege if e["body"]["kind"] == "TRIAL" and e["body"]["family"] == meta.FAMILIE]
    assert phasen == ["BEGINN"] * 2 + ["ERGEBNIS"] * 2
    assert all(e["body"]["modell_sha"] == mf.datei_sha(modelle / f"{e['body']['variant_id']}.json") for e in eintraege
               if e["body"].get("phase") == "ERGEBNIS")
    assert protokoll.vollstaendigkeit(log, lauf="F-05", varianten_ids=NUR) == []
    with pytest.raises(protokoll.ProtokollFehler, match="schon ausgewertet"):                    # genau eine Auswertung je Familie
        meta.ausfuehren(**{**kw, "datum": "2026-10-10"}, vorpruefen=False)
