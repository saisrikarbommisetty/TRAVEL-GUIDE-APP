from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from google import genai
import requests
import base64
import os
import time
from dotenv import load_dotenv

load_dotenv()

FRONTEND_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Frontend"))

app = Flask(__name__, static_folder=FRONTEND_FOLDER)
CORS(app)

def get_gemini_client():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set. Please add GEMINI_API_KEY to your Render Environment Variables.")
    return genai.Client(api_key=key)

PROMPTS = {
    "Summary": """
You are a professional tourist guide.
Provide a high-level overview of "{place}" in {language}.

Focus on:
- The historical significance
- Why the place is famous
- Key architectural or cultural highlights

Keep the explanation concise, engaging, and easy to follow.
Avoid excessive details and dates.
Limit the response to around 200 words.

Respond ONLY in {language}.
""",

    "Detailed": """
You are a professional tourist guide.
Provide a detailed and immersive explanation of "{place}" in {language}.

Cover:
- Historical background and timeline
- Architectural design and unique features
- Cultural importance and notable events
- Interesting facts and visitor insights

Explain concepts clearly and in a storytelling manner.
Include relevant details and examples to create a rich experience.
Limit the response to around 400 words.

Respond ONLY in {language}.
"""
}


def generate_speech(text, voice_id, locale):
    murf_key = os.environ.get("MURF_API_KEY", "").strip()
    if not murf_key:
        print("Warning: MURF_API_KEY is not set. Skipping audio synthesis.")
        return None

    url = "https://global.api.murf.ai/v1/speech/stream"
    headers = {
        "api-key": murf_key,
        "Content-Type": "application/json"
    }
    data = {
        "voice_id": voice_id,
        "text": text,
        "locale": locale,
        "model": "FALCON",
        "format": "MP3",
        "sampleRate": 24000,
        "channelType": "MONO"
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            return response.content
        else:
            print(f"Murf API Error: {response.status_code} - {response.text}")
            return None
    except Exception as ex:
        print(f"Murf request exception: {ex}")
        return None


def generate_description(place, answer_type, language):
    client = get_gemini_client()
    prompt = PROMPTS.get(answer_type, PROMPTS["Summary"]).format(place=place, language=language)
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash"
    ]
    
    last_error = None
    for model in models_to_try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = e
            err_str = str(e)
            print(f"Model {model} error: {err_str[:120]}")
            if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                print(f"Model {model} quota exhausted.")
            continue
                
    if "RESOURCE_EXHAUSTED" in str(last_error) or "429" in str(last_error):
        raise Exception("Google Gemini Free Daily Quota Exceeded for this API key. Please create a fresh API key at https://aistudio.google.com/ or try again when quota resets.")

    raise Exception(f"Failed to generate description: {last_error}")


    
@app.route("/generate-audio-guide", methods=["POST"])
def generate_audio_guide():
    try:
        data = request.get_json(force=True)
        place = data.get("place")
        answer_type = data.get("answerType", "Summary")
        language = data.get("language", "English")
        voice_id = data.get("voiceId", "Matthew")
        locale = data.get("locale", "en-US")

        text_description = generate_description(place, answer_type, language)
        audio_bytes = generate_speech(text_description, voice_id, locale)
        
        encoded_audio = ""
        if audio_bytes:
            encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

        return jsonify({
            "description": text_description,
            "audioBase64": encoded_audio
        })
    except Exception as e:
        print(f"Server error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(FRONTEND_FOLDER, path)):
        return send_from_directory(FRONTEND_FOLDER, path)
    return send_from_directory(FRONTEND_FOLDER, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)