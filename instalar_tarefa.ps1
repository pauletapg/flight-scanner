# Cria (ou atualiza) a tarefa "FlightScanner" no Agendador de Tarefas do Windows.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File instalar_tarefa.ps1
#   powershell -ExecutionPolicy Bypass -File instalar_tarefa.ps1 -Horarios 7,13,19
#
# Para remover: Unregister-ScheduledTask -TaskName FlightScanner

param(
    [int[]]$Horarios = @(1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23),
    [int]$AtrasoMaximoMinutos = 20
)

$pasta = $PSScriptRoot
# pythonw roda sem abrir janela; tudo vai para logs\scanner.log
$pythonw = Join-Path $pasta ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    throw "Não encontrei $pythonw. Crie o ambiente virtual antes (veja o README)."
}

$acao = New-ScheduledTaskAction -Execute "`"$pythonw`"" -Argument "-m scanner.main" -WorkingDirectory $pasta

$gatilhos = foreach ($hora in $Horarios) {
    New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($hora)) `
        -RandomDelay (New-TimeSpan -Minutes $AtrasoMaximoMinutos)
}

# StartWhenAvailable: se o PC estava desligado no horário, roda uma vez quando ligar.
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName "FlightScanner" -Action $acao -Trigger $gatilhos -Settings $opcoes `
    -Description "Busca voos no Google Flights e alerta no WhatsApp (flight scanner)" -Force | Out-Null

$lista = ($Horarios | ForEach-Object { "{0:D2}h" -f $_ }) -join ", "
Write-Host "Tarefa 'FlightScanner' criada. Horários: $lista (+ até $AtrasoMaximoMinutos min aleatórios)."
