@echo off
chcp 65001 >nul
rem Abre a interface do Flight Scanner no navegador. Se o servidor ainda não estiver no ar, sobe com pythonw
rem (sem janela de console); se já estiver, só abre a página. O servidor se desliga pelo botão
rem "Desligar interface" da tela de status. Para a versão de terminal, use "Fast scanner.cmd".
rem
rem Com --rede (ou pelo atalho "Flight Scanner (celular).cmd"), o servidor também atende o celular no mesmo
rem Wi-Fi, mediante um token guardado no .env; o endereço para o celular aparece na tela de status.
cd /d "%~dp0"
set "PORTA=8765"
set "URL=http://127.0.0.1:%PORTA%/"
set "REDE="
if /i "%~1"=="--rede" set "REDE=1"

call :no_ar
if not errorlevel 1 goto ja_no_ar

netstat -ano | findstr /R /C:":%PORTA% .*LISTENING" >nul
if not errorlevel 1 (
    echo A porta %PORTA% já está em uso por outro programa, que não é a interface do Flight Scanner.
    echo Feche esse programa e rode de novo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo Não achei .venv\Scripts\pythonw.exe. Veja a seção Instalação do README.
    pause
    exit /b 1
)
if not exist logs mkdir logs
set "ENDERECO=127.0.0.1"
set "FLIGHT_SCANNER_REDE="
if defined REDE (
    set "ENDERECO=0.0.0.0"
    set "FLIGHT_SCANNER_REDE=1"
)
start "" /b ".venv\Scripts\pythonw.exe" -m uvicorn scanner.web.app:app --host %ENDERECO% --port %PORTA% --no-access-log --no-proxy-headers > "logs\interface.log" 2>&1

set /a tentativas=0
:esperar
call :no_ar
if not errorlevel 1 goto abrir
set /a tentativas+=1
if %tentativas% geq 30 (
    echo A interface não subiu em 30 segundos. Veja logs\interface.log.
    pause
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto esperar

:ja_no_ar
if not defined REDE goto abrir
curl.exe -s -m 2 "%URL%api/acesso" 2>nul | findstr /R /C:"rede.:true" >nul
if errorlevel 1 (
    echo A interface já está aberta, mas sem o acesso pelo celular.
    echo Desligue-a pelo botão "Desligar interface" da tela de status e abra este atalho de novo.
    pause
    exit /b 1
)

:abrir
rem Com o acesso pelo celular, abre direto na tela de status, onde está o endereço para o celular.
if defined REDE (start "" "%URL%#status") else (start "" "%URL%")
exit /b 0

rem Sucesso (errorlevel 0) só se a interface do Flight Scanner responde na porta, e não outro programa.
:no_ar
curl.exe -s -m 2 "%URL%api/rotas" 2>nul | findstr /C:"max_ativas" >nul
exit /b
