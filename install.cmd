@echo off
setlocal enabledelayedexpansion
rem ---------------------------------------------------------------------------
rem  Verlinkt jeden Mod-Ordner dieses Repos in den Subway-Builder-Mods-Ordner.
rem
rem  Nutzt Verzeichnis-Junctions (mklink /J) - die brauchen KEINE
rem  Administratorrechte. Nach einem "git pull" sind die Aenderungen sofort im
rem  Spiel, ohne erneutes Kopieren.
rem
rem  Aufruf:   install.cmd
rem  Optional: install.cmd "D:\anderer\mods\ordner"
rem ---------------------------------------------------------------------------

set "REPO=%~dp0"
set "MODS=%~1"

if "%MODS%"=="" (
    rem Mods-Ordner suchen - der Ordnername unterscheidet sich je Spielversion.
    for %%C in ("%APPDATA%\SubwayBuilder" "%APPDATA%\metro-maker4") do (
        if exist "%%~C" set "MODS=%%~C\mods"
    )
)

if "%MODS%"=="" (
    echo [FEHLER] Kein Subway-Builder-Ordner unter %%APPDATA%% gefunden.
    echo          Pfad zum mods-Ordner bitte als Argument angeben:
    echo          install.cmd "C:\Pfad\zu\mods"
    exit /b 1
)

if not exist "%MODS%" mkdir "%MODS%"
echo Mods-Ordner: %MODS%
echo.

set /a COUNT=0
for /d %%D in ("%REPO%*") do (
    if exist "%%D\manifest.json" (
        set "NAME=%%~nxD"
        set "TARGET=%MODS%\!NAME!"

        rem Vorhandene Verknuepfung entfernen. rmdir loescht nur die Junction,
        rem nicht den Inhalt des Repos.
        if exist "!TARGET!" rmdir "!TARGET!" 2>nul

        if exist "!TARGET!" (
            echo [UEBERSPRUNGEN] !NAME! - dort liegt ein echter Ordner.
            echo                 Bitte von Hand entfernen und neu ausfuehren.
        ) else (
            mklink /J "!TARGET!" "%%D" >nul
            if errorlevel 1 (
                echo [FEHLER] !NAME! konnte nicht verlinkt werden.
            ) else (
                echo [OK] !NAME!
                set /a COUNT+=1
            )
        )
    )
)

echo.
echo !COUNT! Mod(s) verlinkt.
echo Spiel starten und unter Einstellungen ^> Mods aktivieren.
endlocal
