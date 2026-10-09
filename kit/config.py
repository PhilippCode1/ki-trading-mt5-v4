"""Konfiguration aus config/kit_demo.toml (tomllib). Zugangsdaten/Kontonummern sind als Schlüssel verboten.

Rechnerspezifisches (Terminalpfad, Broker-Symbolnamen) steht nicht im Repo, sondern optional in der Ablage des Bot-Benutzers:
<Ablage>/lokal.toml mit nur [terminal] und [symbol_namen] – andere Abschnitte werden abgelehnt (fail-closed), damit dort nie
Schwellen oder Fenster am Repo vorbei geändert werden. Versiegelte Risikowerte und Tor-Schwellen stehen eingefroren in
config/tore.toml (kit/gates).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERBOTEN = ("login", "passw", "server", "konto", "account")
LOKAL_ERLAUBT = {"terminal": {"pfad"}, "symbol_namen": None}      # None = beliebige Symbolnamen


@dataclass(frozen=True)
class Konfiguration:
    terminal_pfad: str
    strategie_symbole: tuple[str, ...]
    probe_symbole: tuple[str, ...]
    symbol_namen: dict[str, str] = field(default_factory=dict)
    deviation: int = 20
    entwicklung: tuple[str, str] = ("2010-01-01", "2021-06-30")
    holdout: tuple[str, str] = ("2021-07-01", "2026-06-30")
    zeitrahmen: tuple[str, ...] = ("D1", "H4", "H1")
    fenster_von: str = "08:00"
    fenster_bis: str = "22:00"
    freitag_bis: str = "20:00"
    kursalter_s: float = 5.0
    korridor_prozent: Decimal = Decimal("1")
    spread_faktor: Decimal = Decimal("3")
    provision_je_lot_seite: Decimal = Decimal("3.25")
    probe_abstand_points: int = 300
    probe_sl_enger_points: int = 100
    probe_sl_enger_nach_s: float = 20.0
    probe_schliessen_nach_s: float = 60.0
    probe_takt_min: float = 10.0
    meldungen_windows: bool = False

    def broker_name(self, symbol: str) -> str:
        return self.symbol_namen.get(symbol, symbol)


def _pruefe(d: dict, pfad: str = "") -> None:
    for k, v in d.items():
        if any(s in k.lower() for s in VERBOTEN):
            raise ValueError(f"Konfiguration: verbotener Schlüssel {pfad}{k} (Zugangsdaten gehören nie in Dateien)")
        if isinstance(v, dict):
            _pruefe(v, f"{pfad}{k}.")


def _lokal() -> dict:
    """<Ablage>/lokal.toml (rechnerspezifisch, nicht im Repo); fehlt sie, gilt nur das Repo."""
    from kit import paths
    try:
        datei = paths.kit_home() / "lokal.toml"
    except paths.AblageFehler:
        return {}
    if not datei.is_file():
        return {}
    roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    _pruefe(roh)
    for abschnitt, werte in roh.items():
        if abschnitt not in LOKAL_ERLAUBT or not isinstance(werte, dict):
            raise ValueError(f"lokal.toml: Abschnitt [{abschnitt}] ist dort nicht erlaubt (nur terminal, symbol_namen)")
        erlaubt = LOKAL_ERLAUBT[abschnitt]
        if erlaubt is not None and set(werte) - erlaubt:
            raise ValueError(f"lokal.toml: in [{abschnitt}] nur {sorted(erlaubt)} erlaubt")
    return roh


def laden(pfad: Path | None = None) -> Konfiguration:
    roh = tomllib.loads((pfad or ROOT / "config" / "kit_demo.toml").read_text(encoding="utf-8"))
    _pruefe(roh)
    if pfad is None:
        for abschnitt, werte in _lokal().items():
            roh[abschnitt] = {**roh.get(abschnitt, {}), **werte}
    d = roh.get("daten", {})
    z = roh.get("zeiten", {})
    w = roh.get("waechter", {})
    p = roh.get("probe", {})
    return Konfiguration(terminal_pfad=str(roh.get("terminal", {}).get("pfad", "")),
                         strategie_symbole=tuple(roh["symbole"]["strategie"]), probe_symbole=tuple(roh["symbole"]["probe"]),
                         symbol_namen=dict(roh.get("symbol_namen", {})), deviation=int(roh.get("ausfuehrung", {}).get("deviation", 20)),
                         entwicklung=(d.get("entwicklung_start", "2010-01-01"), d.get("entwicklung_ende", "2021-06-30")),
                         holdout=(d.get("holdout_start", "2021-07-01"), d.get("holdout_ende", "2026-06-30")),
                         zeitrahmen=tuple(d.get("zeitrahmen", ["D1", "H4", "H1"])),
                         fenster_von=str(z.get("fenster_von", "08:00")), fenster_bis=str(z.get("fenster_bis", "22:00")),
                         freitag_bis=str(z.get("freitag_bis", "20:00")), kursalter_s=float(w.get("kursalter_s", 5)),
                         korridor_prozent=Decimal(str(w.get("korridor_prozent", "1"))),
                         spread_faktor=Decimal(str(w.get("spread_faktor", "3"))),
                         provision_je_lot_seite=Decimal(str(roh.get("kosten", {}).get("provision_je_lot_seite", "3.25"))),
                         probe_abstand_points=int(p.get("abstand_points", 300)), probe_sl_enger_points=int(p.get("sl_enger_points", 100)),
                         probe_sl_enger_nach_s=float(p.get("sl_enger_nach_s", 20)),
                         probe_schliessen_nach_s=float(p.get("schliessen_nach_s", 60)), probe_takt_min=float(p.get("takt_min", 10)),
                         meldungen_windows=bool(roh.get("meldungen", {}).get("windows", False)))
