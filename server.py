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

    # Save uploaded file
    suffix = os.path.splitext(audio_file.filename)[1] or ".m4a"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

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

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
