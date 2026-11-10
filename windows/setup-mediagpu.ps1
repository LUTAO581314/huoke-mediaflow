$ErrorActionPreference='Continue'; $ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$W='C:\mediagpu'
$env:UV_LINK_MODE='copy'; $env:UV_PYTHON_INSTALL_DIR="$W\python"
"== python =="
uv python install 3.12 --no-bin 2>&1 | select -Last 2
$base = Get-ChildItem "$W\python" -Directory | ? { $_.Name -match '^cpython-3\.12\.\d+-windows' -and -not $_.LinkType } | select -First 1
$pyexe = Join-Path $base.FullName 'python.exe'; "base=$pyexe"
"== venv =="
if(-not (Test-Path "$W\venv\Scripts\python.exe")){ uv venv --python $pyexe "$W\venv" 2>&1 | Out-String }
$py="$W\venv\Scripts\python.exe"
& $py -c "import sys;print(sys.version)"
uv pip install --python $py torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124 2>&1 | select -Last 2
uv pip install --python $py faster-whisper demucs==4.0.1 edge-tts soundfile "numpy<2.3" 2>&1 | select -Last 2
& $py -c "import torch,faster_whisper,demucs,edge_tts;print('IMPORT_OK',torch.__version__,torch.cuda.is_available())"
"== whisper large-v3 =="
& $py -c "from huggingface_hub import snapshot_download as s;print(s('Systran/faster-whisper-large-v3',local_dir=r'$W\models\large-v3'))" 2>&1 | select -Last 1
"== demucs model =="
$env:TORCH_HOME="$W\models\torch"
& $py -c "from demucs.pretrained import get_model;get_model('htdemucs');print('htdemucs ok')" 2>&1 | select -Last 1
"== ollama =="
if(-not (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe")){ winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements 2>&1 | select -Last 2 }
[Environment]::SetEnvironmentVariable('OLLAMA_HOST','0.0.0.0:11434','User')
Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
"DONE-SETUP"