from flask import Flask, request, jsonify
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer
from datetime import datetime
import tempfile
import subprocess
import os

app = Flask(__name__)

print("Loading BirdNET analyzer...")
analyzer = Analyzer()
print("BirdNET analyzer ready!")


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "BirdNET server is running"})


@app.route("/analyze", methods=["POST"])
def analyze():
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "No audio file provided"}), 400

    audio_file = request.files["audio"]

    lat = request.form.get("latitude", None)
    lon = request.form.get("longitude", None)

    # The recording is never kept: the upload and the converted file are
    # deleted in the finally below on every path, including a failed save or
    # a failed conversion.
    suffix = os.path.splitext(audio_file.filename or "")[1] or ".m4a"
    tmp_path = None
    wav_path = None
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            audio_file.save(tmp)

        # Convert to wav using ffmpeg
        wav_path = tmp_path.rsplit(".", 1)[0] + ".wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_path, "-ar", "48000", "-ac", "1", wav_path],
                capture_output=True,
                timeout=30,
            )
        except Exception as e:
            return jsonify({"success": False, "error": f"Audio conversion failed: {str(e)}"}), 500

        if not os.path.exists(wav_path):
            return jsonify({"success": False, "error": "Audio conversion produced no output"}), 500

        return _analyze_wav(wav_path, lat, lon)

    finally:
        for path in (tmp_path, wav_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def _analyze_wav(wav_path, lat, lon):
    try:
        recording_kwargs = {
            "analyzer": analyzer,
            "path": wav_path,
            "date": datetime.now(),
            "min_conf": 0.25,
        }

        if lat and lon:
            try:
                recording_kwargs["lat"] = float(lat)
                recording_kwargs["lon"] = float(lon)
            except ValueError:
                pass

        recording = Recording(**recording_kwargs)
        recording.analyze()

        detections = []
        for d in recording.detections:
            detections.append(
                {
                    "species": d["common_name"],
                    "scientific_name": d["scientific_name"],
                    "confidence": round(d["confidence"] * 100, 1),
                    "start_time": d["start_time"],
                    "end_time": d["end_time"],
                }
            )

        detections.sort(key=lambda x: x["confidence"], reverse=True)

        return jsonify({"success": True, "detections": detections})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
