# Herkunft: referenz/reference/research/trials.py (v4-Referenz, Tag konzept-c12-wip), SHA-256
# aa060dd1be7ff699d65d3e03b7c14dd25572040a1c1f063786849689df9ea6a2. Unverändert bis auf diesen Kopf und einen
# privaten Namen (neutral „Assistenz“, F-04 W2); Pin in kit/research/HERKUNFT.md.
"""Forschungslog und Versuchszählung (MP §9.C1, Plan §10, O-TRIAL-1): hashverkettetes, append-only JSONL.

Jeder angesehene Versuch zählt – auch verworfene Agenten-/Assistenz-Ideen und nicht registrierte Varianten. Die Versuchszahl N
und N_eff sind die einzige Vorgabe für DSR und OC (C-06); beide Rechner lesen dieselbe Funktion.
N_eff (Eigenwertmethode, Teilnahmeverhältnis): N_eff = (Σλ)² / Σλ² der Korrelationsmatrix C der Versuchsrenditen.
Wegen Σλ = Spur(C) = N und Σλ² = Spur(C²) = Σ_ij c_ij² gilt N_eff = N² / Σ_ij c_ij²; 1 ≤ N_eff ≤ N.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

KINDS = ("IDEA", "IDEA_REJECTED", "PREREG_DRAFT", "PREREG_SIGNED", "DATA_VIEW", "TRIAL", "HOLDOUT_ACCESS",
         "CHANGE_AFTER_VIEW", "ARCHIVED")
ACTORS = ("NUTZER", "CODING_AGENT", "ASSISTENZ", "RF", "SYSTEM")
SPLITS = ("DEVELOPMENT", "HOLDOUT", "PAPER_FORWARD")
GENESIS = "0" * 64


def entry_hash(prev: str, body: Mapping) -> str:
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")
                          ).hexdigest()


def append(log: list[dict], body: Mapping) -> dict:
    """Neuer Eintrag am Ende (append-only); Pflichtfelder werden fail-closed geprüft."""
    errors = check_body(body)
    if errors:
        raise ValueError(";".join(errors))
    prev = log[-1]["hash"] if log else GENESIS
    entry = {"seq": len(log), "prev": prev, "body": dict(body), "hash": entry_hash(prev, body)}
    log.append(entry)
    return entry


def check_body(b: Mapping) -> list[str]:
    errs = []
    if b.get("kind") not in KINDS:
        errs.append("KIND")
    if b.get("actor") not in ACTORS:
        errs.append("ACTOR")
    if not isinstance(b.get("date"), str) or len(b["date"]) != 10:
        errs.append("DATE")
    if not isinstance(b.get("family"), str) or not b["family"]:
        errs.append("FAMILY")
    if b.get("kind") in ("DATA_VIEW", "TRIAL", "HOLDOUT_ACCESS", "CHANGE_AFTER_VIEW") and not isinstance(b.get("variant_id"), str):
        errs.append("VARIANT")
    if b.get("kind") in ("DATA_VIEW", "HOLDOUT_ACCESS") and b.get("split") not in SPLITS:
        errs.append("SPLIT")
    if b.get("kind") == "HOLDOUT_ACCESS" and not (isinstance(b.get("approval_ref"), str) and b["approval_ref"]):
        errs.append("HOLDOUT_WITHOUT_APPROVAL")
    if b.get("kind") == "HOLDOUT_ACCESS" and not (isinstance(b.get("seal_id"), str) and b["seal_id"]):
        errs.append("HOLDOUT_WITHOUT_SEAL")                 # C06-02: jeder Zugriff gehört zu genau einem Siegel
    if b.get("kind") in ("IDEA_REJECTED", "ARCHIVED") and not b.get("reason"):
        errs.append("REASON")
    return errs


def verify(log: Sequence[Mapping]) -> list[str]:
    """Kette, Reihenfolge und Regeln: gelöschte, veränderte oder umsortierte Einträge werden erkannt; Holdout nur nach
    unterschriebener Vorregistrierung der Familie und mit Freigabebezug; Holdout höchstens einmal je Familie."""
    findings, prev, signed = [], GENESIS, set()
    seen: set[tuple] = set()               # (Familie, Variante) mit Ansicht, Test, Änderung oder Holdout
    opened: dict[str, list[str]] = {}      # Familie -> geöffnete Siegel
    reset_ok: dict[str, bool] = {}         # Familie: Forschungsänderung (CHANGE_AFTER_VIEW mit seal_id) und danach neue Signatur
    for i, e in enumerate(log):
        if e.get("seq") != i or e.get("prev") != prev or e.get("hash") != entry_hash(prev, e.get("body", {})):
            findings.append(f"CHAIN:{i}")
        body = e.get("body", {})
        findings += [f"BODY:{i}:{x}" for x in check_body(body)]
        if body.get("kind") == "PREREG_SIGNED":
            signed.add(body.get("family"))
            if reset_ok.get(body.get("family")) is False:
                reset_ok[body.get("family")] = True
        if body.get("kind") == "CHANGE_AFTER_VIEW" and (body.get("family"), body.get("variant_id")) in seen:
            findings.append(f"CHANGE_AFTER_VIEW_REUSES_VARIANT:{i}")   # C06-06: Änderung nach Sicht = neue Variante (+1 Versuch)
        if body.get("kind") == "CHANGE_AFTER_VIEW" and body.get("seal_id") in opened.get(body.get("family"), []):
            reset_ok[body.get("family")] = False       # Siegel VOID; neue Öffnung erst nach neuer signierter Vorregistrierung
        if body.get("kind") in ("DATA_VIEW", "TRIAL") and body.get("split") == "HOLDOUT":
            findings.append(f"HOLDOUT_VIA_{body.get('kind')}:{i}")
        if body.get("kind") == "HOLDOUT_ACCESS":
            if body.get("family") not in signed:
                findings.append(f"HOLDOUT_BEFORE_SIGNED_PREREG:{i}")
            fam, sid = body.get("family"), body.get("seal_id") or f"OHNE_SIEGEL:{i}"
            reopened = sid in opened.get(fam, []) or (bool(opened.get(fam)) and reset_ok.get(fam) is not True)
            if reopened:
                findings.append(f"HOLDOUT_REOPENED:{i}")
            opened.setdefault(fam, []).append(sid)
            reset_ok.pop(fam, None)
        if body.get("kind") in ("DATA_VIEW", "TRIAL") and body.get("family") not in signed and body.get("split") == "DEVELOPMENT":
            findings.append(f"DATA_VIEW_BEFORE_SIGNED_PREREG:{i}")
        if body.get("kind") in ("DATA_VIEW", "TRIAL", "CHANGE_AFTER_VIEW", "HOLDOUT_ACCESS"):
            seen.add((body.get("family"), body.get("variant_id")))
        prev = e.get("hash", "")
    return findings


def trial_count(log: Iterable[Mapping], family: str | None = None) -> int:
    """N = Anzahl verschiedener Varianten mit Ansicht (DATA_VIEW, TRIAL oder CHANGE_AFTER_VIEW), registriert oder nicht, je Familie
    oder gesamt (FORM-056)."""
    seen = set()
    for e in log:
        b = e.get("body", {})
        if b.get("kind") in ("DATA_VIEW", "TRIAL", "CHANGE_AFTER_VIEW") and (family is None or b.get("family") == family):
            seen.add((b.get("family"), b.get("variant_id")))
    return len(seen)


def n_eff(corr: Sequence[Sequence[float]]) -> float:
    """Teilnahmeverhältnis der Eigenwerte: N² / Σ_ij c_ij² (Diagonale 1, symmetrisch)."""
    n = len(corr)
    if n == 0:
        raise ValueError("leere Matrix")
    for i, row in enumerate(corr):
        if len(row) != n or abs(row[i] - 1.0) > 1e-12:
            raise ValueError("Korrelationsmatrix erwartet (quadratisch, Diagonale 1)")
        for j in range(n):
            if abs(corr[i][j] - corr[j][i]) > 1e-12 or not -1.0 <= corr[i][j] <= 1.0:
                raise ValueError("symmetrisch, Werte in [-1, 1]")
    return n * n / sum(c * c for row in corr for c in row)


@dataclass(frozen=True, eq=False)
class TrialCount(Mapping):
    """Versuchszahl aus dem Forschungslog (einzige Quelle, INT-08): N, N_eff, Geltungsbereich; lesbar wie ein Mapping.
    stats.check_trials nimmt nur diesen Typ an – ein selbst gebautes {"N": …, "N_eff": …} wird abgewiesen."""
    N: int
    N_eff: float
    scope: str

    def __getitem__(self, key: str):
        if key not in ("N", "N_eff", "scope"):
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(("N", "N_eff", "scope"))

    def __len__(self) -> int:
        return 3


def dsr_trials(log: Iterable[Mapping], corr: Sequence[Sequence[float]], family: str | None = None, n_max: int | None = None) -> TrialCount:
    """Eine Quelle für DSR und OC: N aus dem Log, N_eff aus der Korrelation derselben Versuche (Dimension = N).
    Geltungsbereich (C-06, W-09): die Familie – ausgewählt wird innerhalb der Familie, das Versuchsbudget ist je Familie
    vorregistriert; family=None zählt alle Familien (nur für Berichte, z. B. die familienübergreifende Fehlzulassung)."""
    log = list(log)
    n = trial_count(log, family)
    if n_max is not None and n > n_max:
        raise ValueError(f"Versuchsbudget überschritten: {n} > N_max {n_max} (neue Vorregistrierungsversion nötig)")
    if len(corr) != n:
        raise ValueError(f"Korrelationsmatrix hat {len(corr)} Versuche, Log zählt {n}")
    return TrialCount(n, n_eff(corr), family or "ALLE_FAMILIEN")
