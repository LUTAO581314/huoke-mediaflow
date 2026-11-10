$ErrorActionPreference='Continue'; [Console]::OutputEncoding=[Text.Encoding]::UTF8
Stop-Process -Id 14204,30632 -Force -EA SilentlyContinue
$ck='C:\mediagpu\models\torch\hub\checkpoints'; New-Item -ItemType Directory -Force $ck | Out-Null
"== demucs via proxy =="
curl.exe -s -S -L --proxy http://127.0.0.1:7897 --retry 3 -o "$ck\955717e8-8726e21a.th" https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th
(Get-Item "$ck\955717e8-8726e21a.th").Length
$env:TORCH_HOME='C:\mediagpu\models\torch'
& C:\mediagpu\venv\Scripts\python.exe -c "from demucs.pretrained import get_model;get_model('htdemucs');print('htdemucs ok')" 2>&1 | select -Last 1
"== ollama =="
$o="$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
[Environment]::SetEnvironmentVariable('OLLAMA_HOST','0.0.0.0:11434','User')
$env:OLLAMA_HOST='0.0.0.0:11434'
Get-Process ollama* -EA SilentlyContinue | Stop-Process -Force
$a=New-ScheduledTaskAction -Execute $o -Argument 'serve'
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$t=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName 'mediagpu-ollama' -Action $a -Trigger $t -Settings $s -Force | Out-Null
Start-ScheduledTask mediagpu-ollama; Start-Sleep 5
try{(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/version -TimeoutSec 5).Content}catch{"ollama not up $_"}
"== pull =="
$env:OLLAMA_HOST='127.0.0.1:11434'
& $o pull qwen2.5:7b 2>&1 | select -Last 2
& $o list
"DONE-SETUP2"