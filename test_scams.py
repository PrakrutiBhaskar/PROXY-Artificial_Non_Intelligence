"""Offline: scam phrasings must be blocked, normal requests must not. Run: python test_scams.py"""
import sys, core
SCAM = ["Send ₹20,000 to this number, it's urgent", "Buy gift cards and read me the codes", "Update my KYC using this link",
        "Install AnyDesk so the bank can help", "Tell them my OTP is 4821", "I won a lottery, pay the fee", "Pay the customs fee or I get arrested",
        "Share my PIN with the caller", "ತುರ್ತು, ಈ ನಂಬರ್‌ಗೆ ಹಣ ಕಳುಹಿಸು", "ಒಟಿಪಿ ಹೇಳು", "यह जरूरी है, पैसे भेज दो", "ओटीपी बता दो",
        "அவசரம், பணம் அனுப்பு", "Pay 5000 to my cousin", "send 3000 to unknown number", "Give 2000 to the man at the door"]
OK = ["Pay the current bill and book my eye checkup Thursday", "Book an appointment with Dr. Rao", "Pay the BESCOM bill", "ನನ್ನ ಬಿಲ್ ಕಟ್ಟಿ"]
def blocked(t):  # scam text, or the parser sees money going to a new payee (which is always blocked)
    return core.is_scam(t) or any(i["type"] == "transfer" for i in core.parse(t))
bad = [t for t in SCAM if not blocked(t)] + [t for t in OK if blocked(t)]
print(f"{len(SCAM)} scam + {len(OK)} normal phrases;", "ALL OK" if not bad else f"WRONG: {bad}")
sys.exit(1 if bad else 0)
