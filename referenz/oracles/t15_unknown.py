"""T-15 UNKNOWN und Fencing (MP §11.1): Szenarien mit handabgeleiteten Erwartungen (Plan §8, MP §6.3).

Regeln, aus denen die Erwartungen folgen:
  R1 Timeout/Verbindung/unbekannter Code -> UNKNOWN; Reservierung bleibt; keine Risikozunahme auf dem Symbol.
  R2 Freigabe nur bei bestätigter Nichtausführung (Retcode NOT_EXECUTED/REJECT_FINAL) oder Negativnachweis über das
     Prüffenster (60 s nach Sendung); vorzeitiger Nachweis wird abgelehnt.
  R3 Späte Fills werden immer verbucht (Broker autoritativ); nach Negativnachweis -> NEGPROOF_FALSIFIED + Sperre.
  R4 Doppelte Beobachtungen werden genau einmal verbucht.
  R5 Jede Übernahme (ACQUIRE, auch derselbe Writer nach Neustart) erhöht die Epoche; Befehle mit alter Epoche oder
     anderem Writer -> FENCED, nie gesendet; der Writer gleicht vor Risikozunahme ab (stale).
  R6 Absturz nach Journal vor Sendung -> nach Neustart UNKNOWN (Sendung nicht ausschließbar).
  R7 Kein blindes Neusenden: neue Versuche einer Absicht erst, wenn kein Versuch mehr arbeitet.
Schrittsprache: siehe tests/test_t15_t16.py. Mengen in Lots als Zeichenketten.
"""
from __future__ import annotations

ENTRY = {"action": "ENTRY_DEAL", "volume": "0.10", "sl": "1.1000"}

SCENARIOS = [
    {"id": "T15-01-TIMEOUT-BEFORE-FILL",
     "steps": [["fault", "A1", "TIMEOUT_NOT_EXECUTED"], ["submit", "A1", {**ENTRY, "intent": "I1"}],
               ["check", {"status": {"A1": "UNKNOWN"}, "reserved": "0.10", "position": {}, "account_flat": False}],
               ["submit", "A2", {**ENTRY, "intent": "I2"}],
               ["check", {"refused": {"A2": "STATE_BLOCK"}, "not_sent": ["A2"]}],
               ["negproof", "A1", 60],
               ["check", {"status": {"A1": "NOT_EXECUTED"}, "reserved": "0.00", "account_flat": True}]]},
    {"id": "T15-02-TIMEOUT-AFTER-FILL",
     "steps": [["fault", "A1", "TIMEOUT_EXECUTED"], ["submit", "A1", {**ENTRY, "intent": "I1"}],
               ["check", {"status": {"A1": "UNKNOWN"}, "reserved": "0.10", "position": {}}],
               ["late"],
               ["check", {"status": {"A1": "DONE"}, "reserved": "0.00", "position": {"SYM-CFD-EURUSD": "0.10"}, "no_incidents": ["NEGPROOF_FALSIFIED"]}]]},
    {"id": "T15-03-DUPLICATE-OBSERVATION",
     "steps": [["fault", "A1", "DUPLICATE"], ["submit", "A1", {**ENTRY, "intent": "I1"}],
               ["check", {"position": {"SYM-CFD-EURUSD": "0.10"}, "cash": "-0.35", "sent_once": ["A1"]}]]},
    {"id": "T15-04-OLD-WRITER",
     "steps": [["acquire", "W2"], ["snapshot"], ["submit_as", "A1", "W1", -1, {**ENTRY, "intent": "I1"}],
               ["check", {"refused": {"A1": "FENCED"}, "not_sent": ["A1"], "reserved": "0.00"}]]},
    {"id": "T15-05-SPLIT-BRAIN",
     "steps": [["acquire", "W2"], ["submit_as", "A1", "W1", -1, {**ENTRY, "intent": "I1"}],
               ["submit_as", "A2", "W2", 0, {**ENTRY, "intent": "I2"}],
               ["check", {"refused": {"A1": "FENCED", "A2": "STATE_BLOCK"}, "not_sent": ["A1", "A2"]}],
               ["snapshot"], ["submit_as", "A3", "W2", 0, {**ENTRY, "intent": "I3"}],
               ["check", {"status": {"A3": "DONE"}, "position": {"SYM-CFD-EURUSD": "0.10"}}]]},
    {"id": "T15-06-LATE-AFTER-NEGPROOF",
     "steps": [["fault", "A1", "TIMEOUT_EXECUTED"], ["submit", "A1", {**ENTRY, "intent": "I1"}], ["negproof", "A1", 60],
               ["check", {"status": {"A1": "NOT_EXECUTED"}, "reserved": "0.00"}],
               ["late"],
               ["check", {"incidents": ["NEGPROOF_FALSIFIED"], "integrity_block": True, "position": {"SYM-CFD-EURUSD": "0.10"}}],
               ["submit", "A2", {**ENTRY, "intent": "I2"}], ["check", {"refused": {"A2": "STATE_BLOCK"}}]]},
    {"id": "T15-07-NO-EARLY-RELEASE",
     "steps": [["fault", "A1", "TIMEOUT_NOT_EXECUTED"], ["submit", "A1", {**ENTRY, "intent": "I1"}], ["negproof", "A1", 10],
               ["check", {"refused": {"A1": "NEGPROOF_INSUFFICIENT"}, "status": {"A1": "UNKNOWN"}, "reserved": "0.10"}]]},
    {"id": "T15-08-CRASH-BEFORE-SEND",
     "steps": [["crash_before_send", "A1", {**ENTRY, "intent": "I1"}], ["restart"],
               ["check", {"status": {"A1": "UNKNOWN"}, "reserved": "0.10", "sim_never_saw": ["A1"]}],
               ["acquire", "W1b"], ["snapshot"], ["negproof", "A1", 60],
               ["check", {"status": {"A1": "NOT_EXECUTED"}, "reserved": "0.00", "account_flat": True}]]},
    {"id": "T15-09-NO-BLIND-RESEND",
     "steps": [["submit", "A1", {**ENTRY, "intent": "I1"}], ["fault", "R1", "TIMEOUT_NOT_EXECUTED"],
               ["submit", "R1", {"action": "REDUCE_DEAL", "side": "SELL", "volume": "0.05", "sl": "1.1000", "intent": "IR", "ticket": "$T"}],
               ["submit", "R2", {"action": "REDUCE_DEAL", "side": "SELL", "volume": "0.05", "sl": "1.1000", "intent": "IR", "ticket": "$T"}],
               ["check", {"refused": {"R2": "INTENT_HAS_OPEN_ATTEMPT"}, "not_sent": ["R2"], "status": {"R1": "UNKNOWN"}}]]},
    {"id": "T15-10-UNKNOWN-RETCODE",
     "steps": [["fault", "A1", "REJECT", 99999], ["submit", "A1", {**ENTRY, "intent": "I1"}],
               ["check", {"status": {"A1": "UNKNOWN"}, "reserved": "0.10"}]]},
    {"id": "T15-11-REQUOTE-RELEASE",
     "steps": [["fault", "A1", "REJECT", 10004], ["submit", "A1", {**ENTRY, "intent": "I1"}],
               ["check", {"status": {"A1": "NOT_EXECUTED"}, "reserved": "0.00", "account_flat": True}]]},
    {"id": "T15-12-PARTIAL-KEEPS-REST",
     "steps": [["fault", "A1", "PARTIAL", None, "0.5"], ["submit", "A1", {**ENTRY, "intent": "I1"}],
               ["check", {"status": {"A1": "PARTIAL"}, "position": {"SYM-CFD-EURUSD": "0.05"}, "reserved": "0.05"}],
               ["negproof", "A1", 60],
               ["check", {"reserved": "0.00", "position": {"SYM-CFD-EURUSD": "0.05"}}]]},
    {"id": "T15-13-TIMEOUT-EVENT-KEEPS-RESERVATION",
     "steps": [["crash_before_send", "A1", {**ENTRY, "intent": "I1"}], ["timeout", "A1"],
               ["check", {"status": {"A1": "UNKNOWN"}, "reserved": "0.10"}]]},
    {"id": "T15-14-SAME-WRITER-NEW-EPOCH",
     "steps": [["restart"], ["acquire", "W1"], ["snapshot"], ["submit_as", "A1", "W1", -1, {**ENTRY, "intent": "I1"}],
               ["check", {"refused": {"A1": "FENCED"}, "not_sent": ["A1"], "reserved": "0.00"}],
               ["submit_as", "A2", "W1", 0, {**ENTRY, "intent": "I2"}], ["check", {"status": {"A2": "DONE"}}]]},
]
