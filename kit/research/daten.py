"""Lesender Kerzenabzug aus MT5 in eine SQLite-Datei außerhalb des Repos (Plan F-1 §5, F-02).

- Nur über ein Nur-Lese-Terminal (send/check verboten). Nur abgeschlossene Kerzen.
- SHA-256 je Abzug über kanonische Zeilen; Abruf wird wiederholt, bis zweimal derselbe Hash kommt (Terminal-Sync).
- ABGESCHNITTEN: erster Balken > 7 Tage nach dem angeforderten Start, obwohl D1 ältere Daten hat, oder Anzahl ≥ maxbars − 10.
- Holdout-Sperre: Abzüge, die nach dem Ende der Entwicklungsperiode liegen, nur mit ausdrücklicher Holdout-Freigabe (F-06).
- Rohdaten bleiben lokal; zurück an den Aufrufer gehen nur Kennzahlen (Zählungen, Bereiche, Hashes).
- Zeitbasis: Die Kerzenzeiten stehen in SERVERZEIT (der Abzug misst den Serverversatz nicht; Befund F-04, Datenprüfung: Wochenöffnung
  immer Mo 00:00 Serverzeit, der Server folgt der New-Yorker Sommerzeit, UTC+3 bzw. UTC+2). `ziehen` verweigert deshalb ein Terminal
  mit gemessenem Versatz (sonst gemischte Zeitbasen); `lesen(versatz_s=…)` rechnet beim Lesen nach UTC um.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from kit.domain.types import Bar

UTC = dt.UTC
TAG = 86400
DAUER = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}


class HoldoutGesperrt(RuntimeError):
    """Abzug in den Holdout-Zeitraum ohne Freigabe."""


@dataclass(frozen=True)
class Abzug:
    symbol: str
    zeitrahmen: str
    start: str
    ende: str
    anzahl: int
    erster: str
    letzter: str
    sha256: str
    status: str            # OK, ABGESCHNITTEN, INSTABIL, LEER, ZU_KURZ


def _epoch(datum: str, ende: bool = False) -> int:
    t = dt.datetime.fromisoformat(datum).replace(tzinfo=UTC)
    return int(t.timestamp()) + (TAG - 1 if ende else 0)


def _iso(t: int) -> str:
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M")


def kerzen_hash(bars: list[Bar]) -> str:
    h = hashlib.sha256()
    for b in bars:
        h.update(f"{b.time};{b.open};{b.high};{b.low};{b.close};{b.spread_points}\n".encode())
    return h.hexdigest()


def _db(pfad: Path) -> sqlite3.Connection:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE IF NOT EXISTS abzug (id INTEGER PRIMARY KEY, gezogen TEXT, symbol TEXT, zeitrahmen TEXT, start TEXT, "
                "ende TEXT, anzahl INTEGER, erster TEXT, letzter TEXT, sha256 TEXT, status TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS kerze (abzug INTEGER, zeit INTEGER, o TEXT, h TEXT, l TEXT, c TEXT, spread INTEGER, "
                "PRIMARY KEY (abzug, zeit))")
    return con


def ziehen(terminal, symbol: str, zeitrahmen: str, start: str, ende: str, db_pfad: Path, *, holdout_ab: str,
           holdout_frei: bool = False, maxbars: int = 0, d1_erster: int | None = None, versuche: int = 3) -> Abzug:
    if getattr(terminal, "versatz_s", None):
        raise RuntimeError("Abzüge speichern Serverzeit – Terminal mit gemessenem Versatz würde die Zeitbasis mischen (F-04).")
    s, e = _epoch(start), _epoch(ende, ende=True)
    if e >= _epoch(holdout_ab) and not holdout_frei:
        raise HoldoutGesperrt(f"Abzug bis {ende} reicht in den Holdout (ab {holdout_ab}) – nur mit HOLDOUT-OK (F-06).")
    vorher = None
    bars: list[Bar] = []
    status = "INSTABIL"
    for _ in range(versuche):
        bars = [b for b in terminal.bars(symbol, zeitrahmen, s, e) if b.is_closed]
        if not holdout_frei:                      # Kerzen, die über den Holdout-Beginn hinausreichen (D1/H4 auf Servergrenzen), nie
            bars = [b for b in bars if b.time + DAUER.get(zeitrahmen, 0) <= _epoch(holdout_ab)]
        h = kerzen_hash(bars)
        if h == vorher:
            status = "OK"
            break
        vorher = h
    if not bars:
        status = "LEER"
    elif status == "OK":
        if maxbars and len(bars) >= maxbars - 10:
            status = "ABGESCHNITTEN"
        elif bars[0].time > s + 7 * TAG and d1_erster is not None and d1_erster < bars[0].time - 7 * TAG:
            status = "ABGESCHNITTEN"
    a = Abzug(symbol, zeitrahmen, start, ende, len(bars), _iso(bars[0].time) if bars else "", _iso(bars[-1].time) if bars else "",
              kerzen_hash(bars), status)
    con = _db(db_pfad)
    with con:
        cur = con.execute("INSERT INTO abzug (gezogen, symbol, zeitrahmen, start, ende, anzahl, erster, letzter, sha256, status) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?)", (dt.datetime.now(UTC).isoformat(timespec="seconds"), *asdict(a).values()))
        con.executemany("INSERT INTO kerze VALUES (?,?,?,?,?,?,?)",
                        [(cur.lastrowid, b.time, str(b.open), str(b.high), str(b.low), str(b.close), b.spread_points) for b in bars])
    con.close()
    return a


class DatenFehler(RuntimeError):
    """Abzug fehlt, ist nicht OK, passt nicht zu seinem Hash oder reicht in den Holdout (fail-closed)."""


def lesen(db_pfad: Path, symbol: str, zeitrahmen: str, *, start: str, ende: str, holdout_ab: str,
          zwischenspeicher: dict | None = None, soll_sha: str | None = None, versatz_s: int = 0) -> tuple[list[Bar], dict]:
    """Kerzen des jüngsten OK-Abzugs (symbol, zeitrahmen, start, ende) aus der SQLite-Datei – nur lesend (F-04).

    Prüft: Status OK, Anzahl und SHA-256 über alle Kerzen des Abzugs wie beim Abzug (Unversehrtheit). Holdout-Sperre in UTC: eine Kerze,
    die nach holdout_ab beginnt, bricht ab; eine Kerze, die vorher beginnt, aber erst danach endet (D1/H4 auf Servergrenzen, F-02-Abzüge),
    wird verworfen und nie zurückgegeben (Anzahl in den Kennzahlen). zwischenspeicher teilt gleiche Decimal-Werte über alle Kerzen
    (Speicher bei vielen Prozessen). soll_sha: genau dieser Abzug (gebunden an die Datensicht), sonst der jüngste OK-Abzug.
    versatz_s: gespeicherte Serverzeit minus versatz_s = zurückgegebene Zeit (UTC); Hash über die gespeicherten Werte, Holdout-Grenze
    auf den umgerechneten Zeiten.
    Rückgabe: Kerzen und die Kennzahlen des Abzugs (ohne Kurse)."""
    if not Path(db_pfad).is_file():
        raise DatenFehler(f"Datenbank fehlt: {Path(db_pfad).name}")
    con = sqlite3.connect(f"file:{Path(db_pfad).as_posix()}?mode=ro", uri=True)
    try:
        bedingung, werte = ("", ()) if soll_sha is None else (" AND sha256=?", (soll_sha,))
        zeile = con.execute("SELECT id, sha256, anzahl, erster, letzter, status FROM abzug WHERE symbol=? AND zeitrahmen=? AND start=? AND "
                            f"ende=? AND status='OK'{bedingung} ORDER BY id DESC LIMIT 1", (symbol, zeitrahmen, start, ende, *werte)).fetchone()
        if zeile is None:
            raise DatenFehler(f"kein OK-Abzug für {symbol} {zeitrahmen} {start}–{ende}" + (" mit dem Hash der Datensicht" if soll_sha else ""))
        abzug_id, sha, anzahl, erster, letzter, status = zeile
        roh = con.execute("SELECT zeit, o, h, l, c, spread FROM kerze WHERE abzug=? ORDER BY zeit", (abzug_id,)).fetchall()
    finally:
        con.close()
    cache = zwischenspeicher if zwischenspeicher is not None else {}

    def dz(s: str) -> Decimal:
        v = cache.get(s)
        if v is None:
            v = cache[s] = Decimal(s)
        return v
    bars = [Bar(symbol, int(t), dz(o), dz(h), dz(lo), dz(c), int(sp)) for t, o, h, lo, c, sp in roh]
    if len(bars) != anzahl or kerzen_hash(bars) != sha:
        raise DatenFehler(f"{symbol} {zeitrahmen}: Kerzen passen nicht zum Hash des Abzugs (Anzahl/SHA-256)")
    if versatz_s:
        bars = [Bar(symbol, b.time - versatz_s, b.open, b.high, b.low, b.close, b.spread_points) for b in bars]
    grenze = _epoch(holdout_ab)
    if bars and bars[-1].time >= grenze:
        raise HoldoutGesperrt(f"{symbol} {zeitrahmen}: Kerzen ab {holdout_ab} im Entwicklungsabzug – Holdout-Sperre")
    if zeitrahmen not in DAUER:
        raise DatenFehler(f"unbekannter Zeitrahmen {zeitrahmen}")
    behalten = [b for b in bars if b.time + DAUER[zeitrahmen] <= grenze]
    return behalten, {"symbol": symbol, "zeitrahmen": zeitrahmen, "anzahl": anzahl, "erster": erster, "letzter": letzter, "sha256": sha,
                      "status": status, "verworfen_holdout": len(bars) - len(behalten)}


def jahre(a: Abzug) -> float:
    if not a.anzahl:
        return 0.0
    t0 = dt.datetime.strptime(a.erster, "%Y-%m-%d %H:%M")
    t1 = dt.datetime.strptime(a.letzter, "%Y-%m-%d %H:%M")
    return (t1 - t0).days / 365.25
