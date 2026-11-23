# SPDX-License-Identifier: GPL-3.0-or-later
"""
Lokale KI-Tiefenschätzung über ONNX Runtime – keine Cloud, keine Kosten pro Felge.

Modelle (beide Apache-2.0, einmaliger Download):
- HIGH: Depth Anything 3 Mono-Large (q4f16, ~350 MB) – deutlich sauberere Flächen und Kanten
- FAST: Depth Anything V2 Small (quantisiert, ~27 MB) – schnell, etwas rauschiger

Laufzeit: onnxruntime 1.23.2 – letzte Version mit Intel-Mac-Paketen (macOS >= 13),
per pip in einen eigenen Ordner (ohne Abhängigkeiten, Blenders numpy bleibt).
"""
import os
import subprocess
import sys

import numpy as np

ORT_VERSION = "1.23.2"
MODELS = {
    "HIGH": ("https://huggingface.co/Jens-Duttke/Depth-Anything-3-MONO-ONNX/resolve/main/"
             "da-v3-mono-large_q4f16_opset21_optimized.onnx",
             "depth_anything_3_mono_large_q4f16.onnx", np.float16),
    "FAST": ("https://huggingface.co/onnx-community/depth-anything-v2-small/"
             "resolve/main/onnx/model_quantized.onnx",
             "depth_anything_v2_small_q.onnx", np.float32),
}
INPUT = 518  # Vielfaches von 14

_sessions = {}


def data_dir():
    try:
        import bpy
        d = bpy.utils.user_resource("DATAFILES", path="felge3d", create=True)
    except Exception:  # noqa: BLE001 – außerhalb von Blender (Tests)
        d = os.path.join(os.path.expanduser("~"), ".felge3d")
    os.makedirs(d, exist_ok=True)
    return d


def libs_dir():
    d = os.path.join(data_dir(), "libs")
    os.makedirs(d, exist_ok=True)
    if d not in sys.path:
        sys.path.append(d)
    return d


def model_path(kind="HIGH"):
    return os.path.join(data_dir(), MODELS[kind][1])


def runtime_available():
    libs_dir()
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def is_ready(kind="HIGH"):
    return runtime_available() and os.path.isfile(model_path(kind))


def install_runtime():
    """onnxruntime per pip in den Add-on-Datenordner installieren (Blender-Python)."""
    target = libs_dir()
    py = sys.executable
    subprocess.run([py, "-m", "ensurepip", "--upgrade"], check=False,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    r = subprocess.run([py, "-m", "pip", "install", "--no-deps", "--upgrade",
                        "--target", target, "onnxruntime==" + ORT_VERSION, "flatbuffers", "packaging",
                        "protobuf<6"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise RuntimeError("pip-Installation fehlgeschlagen:\n" + r.stdout[-1500:])
    return r.stdout[-300:]


def download_model(kind="HIGH", progress=None):
    """Modell in Blöcken herunterladen (große Datei, nicht komplett im Speicher)."""
    import urllib.request
    from . import updater  # gleiche SSL-Logik
    url = MODELS[kind][0]
    req = urllib.request.Request(url, headers={"User-Agent": "Felge3D"})
    tmp = model_path(kind) + ".tmp"
    total = 0
    with urllib.request.urlopen(req, timeout=60, context=updater._ssl_context()) as r, open(tmp, "wb") as f:
        size = int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            if progress and size:
                progress(total / size)
    if total < 1_000_000 or (size and total != size):
        os.remove(tmp)
        raise RuntimeError("Modell-Download unvollständig (%d von %d Bytes)." % (total, size))
    os.replace(tmp, model_path(kind))
    return total


def _get_session(kind):
    if kind not in _sessions:
        libs_dir()
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        _sessions[kind] = ort.InferenceSession(model_path(kind), opts, providers=["CPUExecutionProvider"])
    return _sessions[kind]


def _resize(img, h, w):
    """Bilineares Skalieren nur mit numpy (für 2D oder HxWxC)."""
    H, W = img.shape[:2]
    ys = np.clip((np.arange(h) + 0.5) * H / h - 0.5, 0, H - 1)
    xs = np.clip((np.arange(w) + 0.5) * W / w - 0.5, 0, W - 1)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    y1 = np.minimum(y0 + 1, H - 1)
    x1 = np.minimum(x0 + 1, W - 1)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    if img.ndim == 3:
        fy = fy[..., None]
        fx = fx[..., None]
    a = img[y0][:, x0]
    b = img[y0][:, x1]
    c = img[y1][:, x0]
    d = img[y1][:, x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def depth_map(rgb, cx, cy, rx, ry, margin=1.08, kind="HIGH"):
    """
    rgb: Arbeitsbild (Zeile 0 = unten, wie in Blender), cx..ry: Felge in Pixeln.
    Gibt Tiefenkarte gleicher Größe zurück (größer = näher), außerhalb des Ausschnitts NaN.
    """
    h, w = rgb.shape[:2]
    x0 = int(max(0, np.floor(cx - rx * margin)))
    x1 = int(min(w, np.ceil(cx + rx * margin)))
    y0 = int(max(0, np.floor(cy - ry * margin)))
    y1 = int(min(h, np.ceil(cy + ry * margin)))
    crop = rgb[y0:y1, x0:x1, :3][::-1]            # für die KI: oben = oben
    x = _resize(crop.astype(np.float32), INPUT, INPUT)
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    sess = _get_session(kind)
    dtype = MODELS[kind][2]
    out = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(dtype)})[0]
    out = np.asarray(out, np.float32).reshape(out.shape[-2:])   # beide Modelle: größer = näher
    d = _resize(out, y1 - y0, x1 - x0)[::-1]
    full = np.full((h, w), np.nan, np.float32)
    full[y0:y1, x0:x1] = d
    return full
