"""Variantenliste der Forschungsrunde F-04 (docs/bot/prereg/F04_ENTWURF.md §2–5), Reihenfolge fest: 8 × S-REV-01 und 4 × S-REV-02
(Familie F04-ZIEL-STOP, 12 gezählte Versuche) sowie S-BL-01 (Familie F04-REFERENZ, zählt nie für das 85-%-Tor).
Variante.parameter = Konstruktorargumente der Strategie (für S-BL-01 die von donchian_ref.Params)."""
from __future__ import annotations

from dataclasses import dataclass

from kit.strategy.donchian_ref import Params
from kit.strategy.rev import Fehlausbruch, MittelwertRueckkehr

FAMILIE_ZIEL_STOP = "F04-ZIEL-STOP"
FAMILIE_REFERENZ = "F04-REFERENZ"


@dataclass(frozen=True)
class Variante:
    id: str
    familie: str
    zaehlt: bool
    parameter: dict


def varianten() -> list[Variante]:
    out = [Variante(f"S-REV-01-k{k:.1f}-z{z:.2f}-r{r}", FAMILIE_ZIEL_STOP, True, {"n": 48, "k": k, "z_tp": z, "r": r})
           for k in (2.0, 2.5) for z in (0.50, 0.75) for r in (2, 3)]
    out += [Variante(f"S-REV-02-L{spanne}-z{z:.1f}", FAMILIE_ZIEL_STOP, True,
                     {"L": spanne, "z_tp": z, "sl_puffer": 0.1, "max_stop_ziel": 3})
            for spanne in (20, 40) for z in (0.5, 1.0)]
    out.append(Variante("S-BL-01", FAMILIE_REFERENZ, False,
                        {"entry_n": 55, "trail_n": 20, "atr_n": 20, "stop_k": 2.0, "entry_bar_mode": "full_bar"}))
    return out


def strategie(v: Variante) -> MittelwertRueckkehr | Fehlausbruch | Params:
    """Strategieobjekt der Variante; für S-BL-01 das Params-Objekt von donchian_ref.run (läuft nie über den Takt)."""
    if v.id.startswith("S-REV-01-"):
        return MittelwertRueckkehr(**v.parameter)
    if v.id.startswith("S-REV-02-"):
        return Fehlausbruch(**v.parameter)
    if v.id == "S-BL-01":
        return Params(**v.parameter)
    raise ValueError(f"unbekannte Variante {v.id}")
