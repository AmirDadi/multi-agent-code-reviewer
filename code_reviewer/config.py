import os

FAST_MODEL = os.getenv("REVIEWER_FAST_MODEL", "gemini/gemini-2.0-flash-lite")
STRONG_MODEL = os.getenv("REVIEWER_STRONG_MODEL", "anthropic/claude-3-5-sonnet-20241022")
MID_MODEL = os.getenv("REVIEWER_MID_MODEL", "anthropic/claude-3-5-haiku-20241022")
STRONGEST_MODEL = os.getenv("REVIEWER_STRONGEST_MODEL", "anthropic/claude-opus-4-5")
