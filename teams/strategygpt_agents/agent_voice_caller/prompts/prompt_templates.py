"""Prompt templates for the Voice Caller agent."""

CALL_ANALYSIS_PROMPT = """Analyze the following phone call transcript and determine the outcome.

TRANSCRIPT:
{transcript}

Classify the call into exactly one of these dispositions:
- interested: The business owner expressed interest in getting a free website
- not_interested: The owner explicitly declined
- voicemail: The call went to voicemail
- callback_requested: The owner asked to be called back at another time
- no_answer: The phone was not answered or the call failed

Respond with a single word: the disposition."""

CALL_SYSTEM_PROMPT = (
    "You are a call outcome analyst. You read phone call transcripts and classify "
    "the result into one of the predefined disposition categories. Be precise — "
    "only mark 'interested' if the owner clearly expressed willingness to proceed."
)
