# Terminal do Fast scanner: abre na pasta do projeto, mostra a ajuda e fica aberto para você digitar os comandos.
$pasta = $PSScriptRoot
Set-Location $pasta
$py = Join-Path $pasta ".venv\Scripts\python.exe"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Fast scanner"

function buscar { & $py -m scanner.buscar @args }
function scanner { & $py -m scanner.main @args }
function relatorio { & $py -m scanner.relatorio @args }

buscar
Write-Host "Digite o comando abaixo (ex.: buscar --listar). Para sair: exit`n"
