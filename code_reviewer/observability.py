import os
import litellm


def setup_langfuse() -> bool:
    """Enable Langfuse tracing via litellm callbacks if credentials are present."""
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        return True
    return False


def trace_meta(stage: str, repo: str, branch: str) -> dict:
    """Return litellm metadata dict for Langfuse trace grouping."""
    return {
        "trace_name": f"code-reviewer/{stage}",
        "tags": [stage, branch],
        "session_id": f"{repo}:{branch}",
    }
