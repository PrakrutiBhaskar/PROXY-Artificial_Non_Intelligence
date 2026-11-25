"""Pre-flight with REAL credentials (run once per environment; each check skips if its key is missing).
  python check_live.py                       # all configured services
  python check_live.py --audio clip.webm --lang kn    # transcribe a REAL recording (do this with an elder's voice)
The voice check is a round trip: TTS speaks a sentence, Scribe transcribes it back, we score the match.
It is synthetic speech, so treat it as a smoke test; real accents and noise are harder. Test real clips too."""
import argparse, difflib, os, sys
import google_data, notify, planner, voice

PH = {"kn": "ನಾನು ವಿದ್ಯುತ್ ಬಿಲ್ ಪಾವತಿಸಬೇಕು ಮತ್ತು ಗುರುವಾರ ಕಣ್ಣಿನ ತಪಾಸಣೆಗೆ ಬುಕ್ ಮಾಡಿ",
      "hi": "बिजली का बिल भर दो और गुरुवार को आँखों का चेकअप बुक करो",
      "ta": "மின் கட்டணம் செலுத்தி வியாழக்கிழமை கண் பரிசோதனை பதிவு செய்",
      "en": "Pay the electricity bill and book my eye checkup on Thursday"}
def report(name, ok, detail=""): print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
def skip(name, why): print(f"[SKIP] {name}: {why}")

ap = argparse.ArgumentParser(); ap.add_argument("--audio"); ap.add_argument("--lang", default="kn"); args = ap.parse_args()
e = os.environ
if args.audio:
    print(voice.stt(open(args.audio, "rb").read(), args.lang)); sys.exit(0)

if not e.get("ELEVENLABS_API_KEY"): skip("ElevenLabs voice round trip", "ELEVENLABS_API_KEY not set")
else:
    for lang, text in PH.items():
        try:
            back = voice.stt(voice.tts(text), lang, "audio/mpeg")
            r = difflib.SequenceMatcher(None, text, back).ratio()
            report(f"voice round trip [{lang}]", r >= 0.6, f"match {r:.0%} -> {back}")
        except Exception as ex: report(f"voice round trip [{lang}]", False, repr(ex)[:120])
if not e.get("ANTHROPIC_API_KEY"): skip("LLM planner", "ANTHROPIC_API_KEY not set")
else:
    for lang, text in PH.items():
        try:
            kinds = sorted(i["type"] for i in planner.llm_actions(text))
            report(f"planner [{lang}]", kinds == ["book", "pay_bill"], kinds)
        except Exception as ex: report(f"planner [{lang}]", False, repr(ex)[:120])
if not all(e.get(k) for k in ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "APPROVER_WHATSAPP")): skip("WhatsApp", "WHATSAPP_* / APPROVER_WHATSAPP not set")
else: report("WhatsApp message sent", notify._send(dict(requester="Amma", what="TEST: pay ₹1 to BESCOM", id="test00"), "approve"), "(check the approver's phone)")
if not e.get("GOOGLE_TOKEN_FILE"): skip("Gmail/Calendar", "GOOGLE_TOKEN_FILE not set")
else:
    try: report("Gmail find_bill", True, google_data.find_bill("BESCOM")); report("Calendar suggest_slot", True, google_data.suggest_slot("thursday"))
    except Exception as ex: report("Gmail/Calendar", False, repr(ex)[:160])
