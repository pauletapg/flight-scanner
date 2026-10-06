@echo off
chcp 65001 >nul
rem Abre a interface do Flight Scanner no navegador. Se o servidor ainda não estiver no ar, sobe com pythonw
rem (sem janela de console); se já estiver, só abre a página. O servidor se desliga pelo botão
rem "Desligar interface" da tela de status. Para a versão de terminal, use "Fast scanner.cmd".
cd /d "%~dp0"
set "PORTA=8765"
set "URL=http://127.0.0.1:%PORTA%/"

call :no_ar
if not errorlevel 1 goto abrir

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
start "" /b ".venv\Scripts\pythonw.exe" -m uvicorn scanner.web.app:app --host 127.0.0.1 --port %PORTA% --no-access-log > "logs\interface.log" 2>&1

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

:abrir
start "" "%URL%"
exit /b 0

rem Sucesso (errorlevel 0) só se a interface do Flight Scanner responde na porta, e não outro programa.
:no_ar
curl.exe -s -m 2 "%URL%api/rotas" 2>nul | findstr /C:"max_ativas" >nul
exit /b
