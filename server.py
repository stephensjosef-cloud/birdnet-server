from flask import Flask, request, jsonify
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer
from datetime import datetime
import tempfile
import os

app = Flask(__name__)

# Load BirdNET analyzer once on startup (takes a few seconds)
print("Loading BirdNET analyzer...")
analyzer = Analyzer()
print("BirdNET analyzer ready!")


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "BirdNET server is running"})


@app.route("/analyze", methods=["POST"])
def analyze():
    # Check if audio file was sent
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "No audio file provided"}), 400

    audio_file = request.files["audio"]

    # Optional: latitude and longitude for better regional accuracy
    lat = request.form.get("latitude", None)
    lon = request.form.get("longitude", None)

    # Save uploaded file to a temp location
    suffix = os.path.splitext(audio_file.filename)[1] or ".m4a"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        # Build recording config
        recording_kwargs = {
            "analyzer": analyzer,
            "path": tmp_path,
            "date": datetime.now(),
            "min_conf": 0.25,  # Minimum confidence threshold (0.0 - 1.0)
        }

        # Add location if provided (improves accuracy)
        if lat and lon:
            try:
                recording_kwargs["lat"] = float(lat)
                recording_kwargs["lon"] = float(lon)
            except ValueError:
                pass

        recording = Recording(**recording_kwargs)
        recording.analyze()

        # Format results
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

        # Sort by confidence (highest first)
        detections.sort(key=lambda x: x["confidence"], reverse=True)

        return jsonify({"success": True, "detections": detections})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
