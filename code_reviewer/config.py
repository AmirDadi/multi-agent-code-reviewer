import os

FAST_MODEL = os.getenv("REVIEWER_FAST_MODEL", "gemini/gemini-2.0-flash-lite")
STRONG_MODEL = os.getenv("REVIEWER_STRONG_MODEL", "gemini/gemini-2.0-flash")
MID_MODEL = os.getenv("REVIEWER_MID_MODEL", "gemini/gemini-2.0-flash")
# Security specialist uses Claude — better reasoning on auth/injection/secrets
SECURITY_MODEL = os.getenv("REVIEWER_SECURITY_MODEL", "claude-haiku-4-5")
STRONGEST_MODEL = os.getenv("REVIEWER_STRONGEST_MODEL", "gemini/gemini-2.0-flash")
