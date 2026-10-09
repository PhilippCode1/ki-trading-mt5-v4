"""Deutsche Kurzberichte (Markdown) mit festem Einordnungssatz (Plan F-1 §6.6)."""
from __future__ import annotations

import datetime as dt
import json

EINORDNUNG = ("Einordnung: Demo-Ergebnisse belegen die Technik, nicht einen Gewinn. Es gibt keinen belegten Handelsvorteil. "
              "Keine Anlageberatung, keine Gewinnzusage.")


def tor_t_markdown(stand: dict) -> str:
    z = [f"# Tor T – Technik-Stand ({dt.date.today():%d.%m.%Y})", "",
         f"**Urteil:** {stand['urteil']}" + (f" – {stand['grund']}" if stand.get("grund") else ""), "",
         f"- mechanik_hash: `{stand['mechanik_hash'][:16]}…`"]
    if "gesendet" in stand:
        m = stand["mindestens"]
        z += [f"- Gesendete Orderoperationen: {stand['gesendet']} (Ziel ≥ {m['min_operationen']}): Eröffnen {stand['eroeffnen']} "
              f"(≥ {m['min_eroeffnen']}), Schließen {stand['schliessen']} (≥ {m['min_schliessen']}), Ändern {stand['aendern']} "
              f"(≥ {m['min_aendern']})",
              f"- Fehlerfrei: {stand['fehlerfrei']} = Quote {float(stand['quote']):.2%} (Tor ≥ {float(stand['quote_min']):.0%}, "
              f"Ziel {float(stand['quote_ziel']):.0%})",
              f"- Absicht → Operation: {float(stand['absicht_zu_operation']):.2%} (lokal abgelehnt: {stand['lokal_abgelehnt']})",
              f"- Skripte: {', '.join(f'{k} {v}' for k, v in sorted(stand['skripte'].items())) or '–'}",
              f"- Kill-Messungen: {len(stand['kills'])}",
              f"- Null-Toleranz-Defekte: {len(stand['defekte'])}"]
        z += [f"  - {d['art']}: {d['text']}" for d in stand["defekte"][:50]]
    z += ["", EINORDNUNG, ""]
    return "\n".join(z)


def json_text(daten: object) -> str:
    return json.dumps(daten, ensure_ascii=False, indent=1, default=str)
