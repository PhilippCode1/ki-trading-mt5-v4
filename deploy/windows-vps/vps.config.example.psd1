# Vorlage der VPS-Konfiguration. Kopieren nach vps.config.psd1 (wird nicht committet) und anpassen.
# Keine Passwoerter, Tokens oder Kontonummern hier eintragen - die gibt der Betreiber nur interaktiv ein.
@{
    # Gemeinsamer Ordner fuer Terminal, Sicherungen und Austausch (Bot-Daten liegen im Profil des Bot-Benutzers)
    Basis            = 'C:\KI-Trading'
    Mt5Ordner        = 'C:\KI-Trading\mt5-demo'
    SicherungOrdner  = 'C:\KI-Trading\sicherung'
    AustauschOrdner  = 'C:\KI-Trading\austausch'

    # Windows-Benutzer: Bot (Demo-Betrieb, Autologon) und Agent (Claude Code, Entwicklung). Live spaeter nur getrennt.
    BotBenutzer      = 'kitbot'
    AgentBenutzer    = 'kitdev'

    # Repo (Bot-Checkout liest nur; Agent-Checkout entwickelt). Wer einen eigenen Fork betreibt, traegt hier dessen URL ein.
    RepoUrl          = 'https://github.com/PhilippCode1/ki-trading-mt5-v4-private.git'
    RepoOrdnerName   = 'ki-trading'

    # Software
    PythonBot        = '3.11'          # MetaTrader5-Wheel 5.0.6090 gibt es fuer cp311
    PythonDev        = '3.12'
    Mt5InstallerUrl  = 'https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe'

    # Betrieb
    WartungsTag      = 'Saturday'      # Updates/Neustarts nur bei geschlossenem Markt
    WartungsStunde   = 6
    AktivVon         = 6               # Windows-Update-Nutzungszeit (kein automatischer Neustart)
    AktivBis         = 23
    SicherungUhrzeit = '23:30'
    SicherungTage    = 30              # aeltere Sicherungen im Ordner werden geloescht

    # Optionen
    RdpNurTailscale  = $false          # erst auf $true, wenn RDP ueber die Tailscale-Adresse getestet ist (sonst Aussperrgefahr)
    Docker           = $false          # nur mit verschachtelter Virtualisierung (WSL2) sinnvoll
}
