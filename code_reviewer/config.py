import os

FAST_MODEL = os.getenv("REVIEWER_FAST_MODEL", "gemini/gemini-2.0-flash-lite")
STRONG_MODEL = os.getenv("REVIEWER_STRONG_MODEL", "claude-sonnet-4-5")
MID_MODEL = os.getenv("REVIEWER_MID_MODEL", "claude-haiku-4-5")
STRONGEST_MODEL = os.getenv("REVIEWER_STRONGEST_MODEL", "claude-opus-4-5")
