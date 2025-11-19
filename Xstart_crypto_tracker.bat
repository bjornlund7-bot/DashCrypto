exit 

@echo off
exit
REM Navigera till mappen där ditt Python-skript ligger
REM VIKTIGT: Sökvägen måste vara inom citattecken p.g.a. mellanslag.

cd "C:\Users\jimmy\OneDrive - RZ Auto CNC AB\Skrivbordet"

REM Starta Python-skriptet i bakgrunden utan att blockera Kommandotolken.
REM 'start "Titel"' skapar ett nytt fönster med titeln "Krypto Spårare".
REM '/min' startar det nya fönstret minimerat.

start "Krypto Spårare" /min python xrp_dash.py

REM Eftersom skriptet nu körs i bakgrunden, kan BAT-filen avslutas omedelbart.
exit