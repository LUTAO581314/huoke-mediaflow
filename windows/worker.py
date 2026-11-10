"""mediagpu worker: GPU jobs for the Mac pipeline. Called over SSH by Mac 'mf'.
Subcommands: asr, sep, sovits, health. Outputs land next to input in the job dir."""
import argparse, json, os, sys, time, subprocess, urllib.request, urllib.error
from pathlib import Path

W = Path(r"C:\mediagpu")
if os.name == "nt":
    site = Path(sys.prefix) / "Lib" / "site-packages"
    for d in [site / "torch" / "lib", *(site / "nvidia").glob("*/bin")]:
        if d.is_dir():
            os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]
            os.add_dll_directory(str(d))

def ts(s):
    ms = round(s * 1000); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def asr(a):
    from faster_whisper import WhisperModel
    t0 = time.perf_counter()
    model = WhisperModel(str(W / "models" / a.model), device="cuda", compute_type="float16")
    import soundfile as sf, numpy as np
    audio, sr = sf.read(a.input, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != 16000:  # Mac 端已转 16k，这里只做兜底的线性重采样
        audio = np.interp(np.arange(0, len(audio), sr / 16000), np.arange(len(audio)), audio).astype(np.float32)
    segs, info = model.transcribe(audio, language=a.language or None, vad_filter=True, beam_size=5,
                                  word_timestamps=True, condition_on_previous_text=False,
                                  initial_prompt=a.prompt or None)
    rows = []
    for s in segs:
        rows.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                     "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word, "p": round(w.probability, 3)} for w in (s.words or [])]})
    out = Path(a.output)
    res = {"status": "transcribed" if rows else "no_speech_detected", "model": a.model, "language": info.language,
           "language_probability": round(info.language_probability, 3), "duration": info.duration,
           "elapsed": round(time.perf_counter() - t0, 2), "segments": rows}
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    out.with_suffix(".srt").write_text("".join(f"{i}\n{ts(r['start'])} --> {ts(r['end'])}\n{r['text']}\n\n" for i, r in enumerate(rows, 1)), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("status", "language", "duration", "elapsed")}, ensure_ascii=False))

def sep(a):
    # 不走 demucs CLI：它会用 subprocess 调 ffprobe（winget 链接在 SSH 会话下报 WinError 448）。
    os.environ["TORCH_HOME"] = str(W / "models" / "torch")
    import torch, soundfile as sf, numpy as np
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    t0 = time.perf_counter()
    model = get_model("htdemucs"); model.eval()
    wav, sr = sf.read(a.input, dtype="float32", always_2d=True)
    if wav.shape[1] == 1: wav = np.repeat(wav, 2, axis=1)
    x = torch.from_numpy(wav.T.copy())
    ref = x.mean(0); m, s = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        out = apply_model(model, ((x - m) / s)[None], device="cuda", shifts=1, split=True, overlap=0.25, progress=False)[0]
    out = out * s + m
    names = model.sources; vi = names.index("vocals")
    vocals = out[vi]; rest = out.sum(0) - vocals
    od = Path(a.outdir); od.mkdir(parents=True, exist_ok=True)
    sf.write(od / "vocals.wav", vocals.cpu().numpy().T, model.samplerate)
    sf.write(od / "no_vocals.wav", rest.cpu().numpy().T, model.samplerate)
    print(json.dumps({"status": "ok", "elapsed": round(time.perf_counter() - t0, 2), "files": ["vocals.wav", "no_vocals.wav"]}))

SOVITS = "http://127.0.0.1:9880"
def sovits_up():
    try:
        urllib.request.urlopen(SOVITS + "/docs", timeout=3); return True
    except Exception:
        return False

def sovits(a):
    if not sovits_up():
        subprocess.run(["schtasks", "/Run", "/TN", "mediagpu-sovits"], capture_output=True)
        for _ in range(120):
            time.sleep(2)
            if sovits_up(): break
        else:
            sys.exit("GPT-SoVITS API did not start on 9880")
    body = {"text": Path(a.text_file).read_text(encoding="utf-8"), "text_lang": a.lang,
            "ref_audio_path": str(Path(a.ref).resolve()), "prompt_text": a.ref_text or "", "prompt_lang": a.ref_lang or a.lang,
            "text_split_method": "cut5", "speed_factor": a.speed, "media_type": "wav", "streaming_mode": False}
    req = urllib.request.Request(SOVITS + "/tts", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            Path(a.output).write_bytes(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"SoVITS {e.code}: {e.read().decode('utf-8', 'replace')[:800]}")
    print(json.dumps({"status": "ok", "elapsed": round(time.perf_counter() - t0, 2)}))

def health(a):
    import torch
    print(json.dumps({"cuda": torch.cuda.is_available(), "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                      "models": sorted(p.name for p in (W / "models").iterdir()), "sovits": sovits_up()}))

p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="cmd", required=True)
x = sp.add_parser("asr"); x.add_argument("input"); x.add_argument("output"); x.add_argument("--language"); x.add_argument("--model", default="large-v3"); x.add_argument("--prompt")
x = sp.add_parser("sep"); x.add_argument("input"); x.add_argument("outdir")
x = sp.add_parser("sovits"); x.add_argument("text_file"); x.add_argument("output"); x.add_argument("--lang", default="zh"); x.add_argument("--ref", required=True); x.add_argument("--ref-text"); x.add_argument("--ref-lang"); x.add_argument("--speed", type=float, default=1.0)
sp.add_parser("health")
a = p.parse_args(); {"asr": asr, "sep": sep, "sovits": sovits, "health": health}[a.cmd](a)
