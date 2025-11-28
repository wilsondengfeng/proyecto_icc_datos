from flask import Blueprint, request, jsonify, current_app
import time
from collections import deque

bp = Blueprint("telemetria", __name__)

# Buffer en memoria por dispositivo y por sensor/actuador (ultimos N por campo)
# Ej: {device: {"temp": deque([{"ts":..., "value":...}]), "hum": deque([...]), ...}}
_buffers = {}
_MAX_ITEMS = 200


def _check_token(req):
    expected = current_app.config.get("API_TOKEN", "")
    if not expected:
        return True  # sin token configurado, acceso libre
    return req.headers.get("X-API-Key") == expected


def _store(payload):
    dev = payload["device"]
    ts = payload["ts"]
    if dev not in _buffers:
        _buffers[dev] = {}
    for key, value in payload.items():
        if key in ("device", "ts"):
            continue
        if key not in _buffers[dev]:
            _buffers[dev][key] = deque(maxlen=_MAX_ITEMS)
        _buffers[dev][key].append({"ts": ts, "value": value})


@bp.route("/api", methods=["POST"])
def recibir():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    temp, hum = data.get("temp"), data.get("hum")
    dev = data.get("device", "esp32")
    motion = data.get("motion")
    led1 = data.get("led1")
    led2 = data.get("led2")
    door_open = data.get("door_open")
    door_angle = data.get("door_angle")
    if temp is None or hum is None:
        return jsonify({"error": "temp y hum requeridos"}), 400
    payload = {
        "temp": float(temp),
        "hum": float(hum),
        "device": dev,
        "ts": time.time(),
    }
    if motion is not None:
        payload["motion"] = bool(motion)
    if led1 is not None:
        payload["led1"] = bool(led1)
    if led2 is not None:
        payload["led2"] = bool(led2)
    if door_open is not None:
        payload["door_open"] = bool(door_open)
    if door_angle is not None:
        payload["door_angle"] = float(door_angle)
    _store(payload)
    return jsonify({"ok": True}), 200


@bp.route("/api", methods=["GET"])
def listar():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    limit = int(request.args.get("limit", 50))
    out = []
    for dev, sensors in _buffers.items():
        for name, readings in sensors.items():
            for entry in list(readings)[-limit:]:
                out.append(
                    {
                        "device": dev,
                        "sensor": name,
                        "value": entry["value"],
                        "ts": entry["ts"],
                    }
                )
    out.sort(key=lambda x: x["ts"], reverse=True)
    return jsonify(out[:limit]), 200
