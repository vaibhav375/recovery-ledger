"""Hand-authored gold set for reply-intent classification.

Why this exists. The first attempt at validation used the LLM-generated
persona corpus, whose labels come free because the intent produced the text.
That measured **42.9%** accuracy — but inspecting the disagreements showed
the fault was mostly in the corpus, not the classifier. qwen2.5:3b, asked to
write as a customer who has already paid, produced lines like "Waste of time
with all these chase msgs" (not a payment claim at all) and "Aur message mat
bhijo mujhse" — which literally means *stop messaging me*, i.e. the opt-out
intent, filed under `paid`. Hindi output was frequently incoherent, and
Hindi accuracy was 27.3% against 62.5% for English.

A labelled set whose labels are wrong cannot validate anything. So the
headline accuracy number is measured against this file instead: examples
written by hand, each chosen to express exactly one intent with no
reasonable second reading. The generated corpus is still evaluated and
reported alongside, as evidence of how much of that 42.9% was label noise.

Every example is a plausible reply to a payment-recovery message, in the
register Indian customers actually use.
"""

from __future__ import annotations

from recovery_ledger.events.schemas import Language
from recovery_ledger.listener.listener import ReplyIntent

# (text, intent, language)
GOLD: list[tuple[str, ReplyIntent, Language]] = [
    # --- PAID -------------------------------------------------------------
    ("I already paid this on Monday, please check your records", ReplyIntent.PAID, Language.EN),
    ("payment done last week itself, check your side", ReplyIntent.PAID, Language.EN),
    ("The amount was debited from my account already", ReplyIntent.PAID, Language.EN),
    ("maine paisa bhej diya hai kal hi, apna record dekho", ReplyIntent.PAID, Language.HINGLISH),
    ("bhai already payment ho chuka hai, screenshot bhejun kya", ReplyIntent.PAID, Language.HINGLISH),
    ("मैंने यह भुगतान पहले ही कर दिया है, कृपया जाँच करें", ReplyIntent.PAID, Language.HI),
    ("पैसे मेरे खाते से कट चुके हैं", ReplyIntent.PAID, Language.HI),

    # --- PROMISE_TO_PAY ---------------------------------------------------
    ("I will pay on the 5th when my salary comes", ReplyIntent.PROMISE_TO_PAY, Language.EN),
    ("Can pay by month end, bit short right now", ReplyIntent.PROMISE_TO_PAY, Language.EN),
    ("will clear it next week for sure", ReplyIntent.PROMISE_TO_PAY, Language.EN),
    ("abhi paise nahi hai, 5 tarikh ko salary aayegi tab kar dunga", ReplyIntent.PROMISE_TO_PAY, Language.HINGLISH),
    ("agle hafte pakka pay kar dunga bhai", ReplyIntent.PROMISE_TO_PAY, Language.HINGLISH),
    ("मैं अगले महीने की पहली तारीख को भुगतान कर दूँगा", ReplyIntent.PROMISE_TO_PAY, Language.HI),
    ("सैलरी आते ही पैसे भेज दूँगा", ReplyIntent.PROMISE_TO_PAY, Language.HI),

    # --- DISPUTE ----------------------------------------------------------
    ("This amount is wrong, I never signed up for this", ReplyIntent.DISPUTE, Language.EN),
    ("I was charged twice for the same thing, this is incorrect", ReplyIntent.DISPUTE, Language.EN),
    ("I cancelled this subscription months ago, why am I being billed", ReplyIntent.DISPUTE, Language.EN),
    ("ye amount galat hai, maine itna kabhi authorise nahi kiya", ReplyIntent.DISPUTE, Language.HINGLISH),
    ("maine to subscription band kar diya tha, phir charge kyun hua", ReplyIntent.DISPUTE, Language.HINGLISH),
    ("यह राशि गलत है, मैंने इतने का भुगतान तय नहीं किया था", ReplyIntent.DISPUTE, Language.HI),
    ("मुझसे दो बार पैसे लिए गए हैं, यह गलत है", ReplyIntent.DISPUTE, Language.HI),

    # --- OPT_OUT ----------------------------------------------------------
    ("Stop messaging me, remove my number from your list", ReplyIntent.OPT_OUT, Language.EN),
    ("Do not contact me again about this", ReplyIntent.OPT_OUT, Language.EN),
    ("unsubscribe me, I don't want these messages", ReplyIntent.OPT_OUT, Language.EN),
    ("mujhe aur message mat bhejo, number hata do", ReplyIntent.OPT_OUT, Language.HINGLISH),
    ("bas karo, ab koi message nahi chahiye mujhe", ReplyIntent.OPT_OUT, Language.HINGLISH),
    ("मुझे और संदेश मत भेजिए, मेरा नंबर हटा दीजिए", ReplyIntent.OPT_OUT, Language.HI),
    ("कृपया मुझसे दोबारा संपर्क न करें", ReplyIntent.OPT_OUT, Language.HI),

    # --- WRONG_PERSON -----------------------------------------------------
    ("Wrong number, I don't know who this person is", ReplyIntent.WRONG_PERSON, Language.EN),
    ("This is not my account, you have the wrong contact", ReplyIntent.WRONG_PERSON, Language.EN),
    ("You've got the wrong number, I have no account with you", ReplyIntent.WRONG_PERSON, Language.EN),
    ("galat number hai bhai, ye mera account nahi hai", ReplyIntent.WRONG_PERSON, Language.HINGLISH),
    ("main ye vyakti nahi hun, kisi aur ka number hoga", ReplyIntent.WRONG_PERSON, Language.HINGLISH),
    ("यह मेरा खाता नहीं है, आपने गलत नंबर पर संदेश भेजा है", ReplyIntent.WRONG_PERSON, Language.HI),
    ("मैं वह व्यक्ति नहीं हूँ जिसे आप ढूँढ रहे हैं", ReplyIntent.WRONG_PERSON, Language.HI),

    # --- NEGOTIATE --------------------------------------------------------
    ("Can I pay half now and the rest next month", ReplyIntent.NEGOTIATE, Language.EN),
    ("If you reduce it by 10% I can settle today", ReplyIntent.NEGOTIATE, Language.EN),
    ("Can we do an instalment plan for this amount", ReplyIntent.NEGOTIATE, Language.EN),
    ("aadha abhi de dun aur aadha agle mahine, chalega kya", ReplyIntent.NEGOTIATE, Language.HINGLISH),
    ("thoda discount de do to aaj hi settle kar deta hun", ReplyIntent.NEGOTIATE, Language.HINGLISH),
    ("क्या मैं इसे किस्तों में चुका सकता हूँ", ReplyIntent.NEGOTIATE, Language.HI),
    ("अगर कुछ छूट मिल जाए तो मैं आज ही भुगतान कर दूँ", ReplyIntent.NEGOTIATE, Language.HI),
]


def gold_replies():
    from recovery_ledger.sim.personas import LabelledReply
    return [LabelledReply(text=t, intent=i, language=l) for t, i, l in GOLD]
