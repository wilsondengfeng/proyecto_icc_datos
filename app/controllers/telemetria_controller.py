from flask import Blueprint, request, jsonify, current_app
import time
from collections import deque

bp = Blueprint("telemetria", __name__)

# Buffer en memoria por dispositivo y por sensor/actuador (ultimos N por campo)
# Ej: {device: {"temp": deque([{"ts":..., "value":...}]), "hum": deque([...]), ...}}
_buffers = {}
_MAX_ITEMS = 200
# Estado de control deseado por dispositivo (led1, led2, door_open, door_angle)
_controls = {}


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


def _set_control(dev, updates):
    ts = time.time()
    if dev not in _controls:
        _controls[dev] = {}
    for k, v in updates.items():
        _controls[dev][k] = {"ts": ts, "value": v}
    return {"ok": True, "device": dev, "updated": list(updates.keys())}


@bp.route("/api/control", methods=["POST"])
def set_control():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    dev = data.get("device", "esp32")
    fields = ["led1", "led2", "door_open", "door_angle"]
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        return jsonify({"error": "sin parametros de control"}), 400
    return jsonify(_set_control(dev, updates)), 200


@bp.route("/api/control", methods=["GET"])
def get_control():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device")
    out = []
    for d, controls in _controls.items():
        if dev and d != dev:
            continue
        for name, entry in controls.items():
            out.append(
                {
                    "device": d,
                    "control": name,
                    "value": entry["value"],
                    "ts": entry["ts"],
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["ts"])),
                }
            )
    out.sort(key=lambda x: x["ts"], reverse=True)
    return jsonify(out), 200


def _latest_reading(sensor_name, dev=None):
    """Devuelve el ultimo valor de un sensor/actuador desde _buffers."""
    candidates = []
    for device, sensors in _buffers.items():
        if dev and device != dev:
            continue
        if sensor_name in sensors and len(sensors[sensor_name]) > 0:
            entry = list(sensors[sensor_name])[-1]
            candidates.append(
                {
                    "device": device,
                    "sensor": sensor_name,
                    "value": entry["value"],
                    "ts": entry["ts"],
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["ts"])),
                }
            )
    if not candidates:
        return None
    return max(candidates, key=lambda x: x["ts"])


def _sensor_get_response(name):
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device")
    reading = _latest_reading(name, dev)
    if not reading:
        return jsonify({"error": "no data"}), 404
    return jsonify(reading), 200


@bp.route("/api/temp", methods=["GET"])
def get_temp():
    return _sensor_get_response("temp")


@bp.route("/api/hum", methods=["GET"])
def get_hum():
    return _sensor_get_response("hum")


@bp.route("/api/motion", methods=["GET"])
def get_motion():
    return _sensor_get_response("motion")


@bp.route("/api/led1", methods=["GET"])
def get_led1():
    return _sensor_get_response("led1")


@bp.route("/api/led2", methods=["GET"])
def get_led2():
    return _sensor_get_response("led2")


@bp.route("/api/door_open", methods=["GET"])
def get_door_open():
    return _sensor_get_response("door_open")


@bp.route("/api/door_angle", methods=["GET"])
def get_door_angle():
    return _sensor_get_response("door_angle")


@bp.route("/api/led1/on", methods=["POST"])
def led1_on():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"led1": True})), 200


@bp.route("/api/led1/off", methods=["POST"])
def led1_off():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"led1": False})), 200


@bp.route("/api/led2/on", methods=["POST"])
def led2_on():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"led2": True})), 200


@bp.route("/api/led2/off", methods=["POST"])
def led2_off():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"led2": False})), 200


@bp.route("/api/door/open", methods=["POST"])
def door_open_cmd():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"door_open": True})), 200


@bp.route("/api/door/close", methods=["POST"])
def door_close_cmd():
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"door_open": False})), 200


@bp.route("/api/door/angle/<int:angle>", methods=["POST"])
def door_angle_cmd(angle):
    if not _check_token(request):
        return jsonify({"error": "unauthorized"}), 401
    dev = request.args.get("device", "esp32-1")
    return jsonify(_set_control(dev, {"door_angle": angle})), 200
