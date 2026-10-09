"""Ende-zu-Ende der Runde 3 (F-05b) auf einer synthetischen Datenbank, ohne scikit-learn (Training durch eine feste Attrappe ersetzt):
Vorregistrierung → Datensicht F05B-DATEN → BEGINN → Modelle (kompakt, verlustfrei, nie überschrieben) → Takt mit dem Richtungsfilter in drei
Kostenprofilen → Parität (Signal, Trade, Datensatz ↔ Takt) → Bericht → ERGEBNIS; zweite Auswertung verweigert.
Privat: braucht config/kostenprofil/f04_startwerte.json (nicht im Spiegel)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

import pytest

from kit.research import entwicklung, meta, protokoll, trials
from kit.research import richtung as ri
from kit.strategy import meta_filter as mf
from kit_tests import backtest_hilfen as bh

pytestmark = pytest.mark.privat
START = int(dt.datetime(2012, 5, 6, 21, 0, tzinfo=dt.UTC).timestamp())
NUR = ("F05B-REV01-LOGREG", "F05B-REV01-HGB")


def utc(*a) -> int:
    return int(dt.datetime(*a, tzinfo=dt.UTC).timestamp())


def _plan() -> list[dict]:
    aus = []
    for von, bis in ((utc(2013, 1, 1), utc(2013, 1, 22)), (utc(2013, 1, 22), utc(2013, 2, 12)), (utc(2013, 2, 12), None)):
        aus.append({"test_von": von, "test_bis": bis, "embargo_bis": meta.embargo_ende(von), "fit_von": von - 12 * 7 * 86400,
                    "val_von": von - 4 * 7 * 86400, "holdout": bis is None})
    return aus


def attrappe(zeilen, v, plan) -> dict:
    """Feste Modelle je Fenster: LOGREG über alle Merkmale (Kauf und Verkauf verschieden) bzw. ein kleines HGB; Grenzen wie der Trainer."""
    namen = mf.merkmal_namen(v.art)
    basis = meta.basis_strategie(v.basis_id)

    def grenzen(zs):
        return {"n": len(zs), "min_t_ent": min((z["t_ent"] for z in zs), default=None), "max_t_ent": max((z["t_ent"] for z in zs), default=None),
                "max_t_exit": max((z["t_exit"] for z in zs), default=None)}

    def modell(seite, training):
        if v.modell == "HGB":
            vz = 1.0 if seite == "k" else -1.0
            return {"art": "HGB", "merkmale": list(namen), "basis": 0.0, "training": training,
                    "baeume": [[[0.0, 0, 0.0, True, 1, 2, False], [0.4 * vz, 0, 0.0, False, 0, 0, True], [-0.4 * vz, 0, 0.0, False, 0, 0, True]],
                               [[0.0, 5, 0.0, True, 1, 2, False], [0.2 * vz, 0, 0.0, False, 0, 0, True], [-0.1 * vz, 0, 0.0, False, 0, 0, True]]]}
        koef = [(-0.6, 0.3, 40.0, -0.5, -8.0, 0.2, 0.4, -0.7, 0.3, -0.2, 0.1, -0.1, 0.2, 0.0, -0.2, 0.3, -0.3)[i] * (1 if seite == "k" else -1)
                for i in range(len(namen))]
        return {"art": "LOGREG", "merkmale": list(namen), "mittel": [0.0] * len(namen), "skala": [1.0] * len(namen),
                "koeffizienten": koef, "achsenabschnitt": 0.1, "training": training}

    def fenster(f):
        innen = ri.menge(zeilen, f["fit_von"], f["val_von"])
        final, val = ri.menge(zeilen, f["fit_von"], f["test_von"]), ri.menge(zeilen, f["val_von"], f["test_von"])
        training = {"fit_von": f["fit_von"], "fit_bis": f["test_von"], "n": len(final), "max_t_ent": max(z["t_ent"] for z in final),
                    "max_t_exit": max(z["t_exit"] for z in final), "val_von": f["val_von"],
                    "val_max_t_exit": max((z["t_exit"] for z in val), default=0)}
        return {**{k: f[k] for k in ri.PLAN_SCHLUESSEL}, "schwelle": 0.05, "modell_kauf": modell("k", training),
                "modell_verkauf": modell("v", training), "grenzen": {"innen": grenzen(innen), "validierung": grenzen(val), "final": grenzen(final)},
                "n_final": len(final), "n_validierung": len(val), "validierung": {"quote": 0.6, "n": len(val)}}
    alle = [fenster(f) for f in plan]
    return {"schema": "richtung/1", "lauf": "F-05b", "variante": v.id, "basis_variante": v.basis_id, "basis_name": basis.name,
            "basis_parameter": basis.parameter(), "art": v.art, "modell_art": v.modell, "merkmale": list(namen),
            "datensatz_sha": hashlib.sha256(meta.datensatz_text(zeilen).encode("utf-8")).hexdigest(),
            "fenster": [f for f, p in zip(alle, plan, strict=True) if not p["holdout"]],
            "holdout": next(f for f, p in zip(alle, plan, strict=True) if p["holdout"]), "paritaet_max": 0.0}


def _prereg(log, familien, lauf, sha) -> None:
    for familie in familien:
        protokoll.anhaengen({"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": "2026-10-09", "family": familie, "lauf": lauf,
                             "prereg_sha": sha, "commit": "0" * 40, "code": {}}, log)


def test_runde3_ende_zu_ende(tmp_path):
    db = tmp_path / "entwicklung.sqlite"
    bh.synthetische_db(db, start=START, wochen=40, saat=3, sigma=0.0022)
    log = tmp_path / "versuchsprotokoll.jsonl"
    ds, modelle = tmp_path / "ds", tmp_path / "modelle"
    _prereg(log, protokoll.FAMILIEN, "TEST", protokoll.PREREG_SHA)
    entwicklung.kostenprofil_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, spread_pfad=tmp_path / "sp.json", vorpruefen=False)
    with pytest.raises(protokoll.ProtokollFehler, match="F-05b"):
        ri.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    _prereg(log, protokoll.FAMILIEN_F05B, "F-05b", protokoll.PREREG_F05B_SHA)
    d = ri.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    assert set(d["datensaetze"]) == set(ri.BASEN) and all(x["zeilen"] > 0 for x in d["datensaetze"].values())
    sicht = [e for e in protokoll.lesen(log) if e["body"]["kind"] == "DATA_VIEW" and e["body"]["family"] == ri.FAMILIE_DATEN][-1]
    assert '"x"' not in json.dumps(sicht["body"]) and sicht["body"]["datensaetze"][meta.BASIS_REV01]["zaehlung"]["nicht_handelbar"] > 0
    with pytest.raises(protokoll.ProtokollFehler, match="schon"):
        ri.daten_eintragen(datum="2026-10-09", db=db, protokoll_pfad=log, ordner=ds, vorpruefen=False)
    kw = {"datum": "2026-10-09", "trainer": attrappe, "prozesse": 4, "db": db, "protokoll_pfad": log, "datensatz_ordner": ds,
          "modell_ordner": modelle, "bericht_ordner": tmp_path, "melden": lambda *_: None, "nur": NUR, "plan_werte": _plan()}
    with pytest.raises(protokoll.ProtokollFehler):                                               # Vorprüfung vor der Auswertung
        ri.ausfuehren(**kw)
    erg = ri.ausfuehren(**kw, vorpruefen=False)
    b = json.loads((tmp_path / "2026-10-09_runde3.json").read_text(encoding="utf-8"))
    md = (tmp_path / "2026-10-09_runde3.md").read_text(encoding="utf-8")
    assert [v["id"] for v in b["varianten"]] == list(NUR) and erg["auswahl"] in (None, *NUR)
    for v in b["varianten"]:
        h = v["haupt"]
        assert h["technik_ok"] and h["paritaet"]["signale"]["quote"] == 1.0 and h["paritaet"]["trades"]["quote"] == 1.0
        assert h["bewertung"]["kriterien"]["technik"]["wert"]["datensatz_paritaet"] == 1.0 and h["bewertung"]["kriterien"]["technik"]["ok"]
        assert v["training"]["datensatz_paritaet"]["takt"] > 0 and h["bewertung"]["kennzahlen"]["n"] > 0
        w = v["training"]["wirkung"]
        assert w["entscheidungen"].get("HANDELN", 0) > 0 and 0 < w["anteil_kauf"] < 1 and w["quote_zufall"] is not None
        assert v["kosten_x1_5"]["trades"] > 0 and v["gegenprobe_3_25"]["trades"] > 0
    for teil in ("Richtungsvorsprung im Datensatz", "Schwellen d* je Testfenster", "Grenzen dieser Auswertung", "Keine Anlageberatung"):
        assert teil in md
    text = json.dumps(b) + json.dumps(protokoll.lesen(log)) + md
    swaps = {w for paar in entwicklung.startwerte()["swap_punkte"].values() for w in paar}
    assert not any(re.search(rf"(?<![\d.]){re.escape(w)}(?!\d)", text) for w in swaps) and "median" not in json.dumps(b)
    hgb = json.loads((modelle / "F05B-REV01-HGB.json").read_text(encoding="utf-8"))
    assert "baeume_kompakt" in hgb["fenster"][0]["modell_kauf"] and "baeume" not in hgb["fenster"][0]["modell_kauf"]
    eintraege = protokoll.lesen(log)
    assert trials.verify(eintraege) == [] and trials.trial_count(eintraege, ri.FAMILIE) == 2
    phasen = [e["body"].get("phase") for e in eintraege if e["body"]["kind"] == "TRIAL" and e["body"]["family"] == ri.FAMILIE]
    assert phasen == ["BEGINN"] * 2 + ["ERGEBNIS"] * 2
    assert all(e["body"]["modell_sha"] == mf.datei_sha(modelle / f"{e['body']['variant_id']}.json") for e in eintraege
               if e["body"].get("phase") == "ERGEBNIS")
    assert protokoll.vollstaendigkeit(log, lauf="F-05b", varianten_ids=NUR) == []
    with pytest.raises(protokoll.ProtokollFehler, match="schon ausgewertet"):
        ri.ausfuehren(**{**kw, "datum": "2026-10-10"}, vorpruefen=False)
