"""Voice via ElevenLabs: Scribe (speech-to-text) and TTS. Needs ELEVENLABS_API_KEY.
Kannada TTS needs Eleven v3 or newer (Multilingual v2 has no Kannada), so the model is configurable.
For India data residency set ELEVENLABS_API_BASE=https://api.in.residency.elevenlabs.io"""
import json, os, urllib.request, uuid

def _key(): return os.environ.get("ELEVENLABS_API_KEY")
def _base(): return os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io")
def config(): return {"tts": bool(_key()), "stt": bool(_key())}

def tts(text):
    vid = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    body = {"text": text, "model_id": os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_v3")}
    req = urllib.request.Request(f"{_base()}/v1/text-to-speech/{vid}", json.dumps(body).encode(),
          {"xi-api-key": _key(), "content-type": "application/json", "accept": "audio/mpeg"})
    return urllib.request.urlopen(req, timeout=20).read()

def stt(audio, lang="kn", mime="audio/webm"):
    """lang: ISO code such as kn / hi / ta / en (a 'kn-IN' style tag is trimmed)."""
    b = uuid.uuid4().hex
    fields = {"model_id": os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2"), "language_code": lang.split("-")[0]}
    parts = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    parts += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.webm"\r\nContent-Type: {mime}\r\n\r\n').encode()
    parts += audio + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(f"{_base()}/v1/speech-to-text", parts,
          {"xi-api-key": _key(), "content-type": f"multipart/form-data; boundary={b}"})
    return json.load(urllib.request.urlopen(req, timeout=30)).get("text", "")
