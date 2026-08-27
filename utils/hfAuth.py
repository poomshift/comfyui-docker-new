import os
from urllib.parse import urlparse

# Environment variables checked, in order, for a Hugging Face access token.
_TOKEN_ENV_VARS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN")

_HF_HOSTS = ("huggingface.co", "hf.co")


def get_hf_token(explicit_token=None):
    """Return the token to use, preferring one passed in over the environment"""
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    for name in _TOKEN_ENV_VARS:
        value = (os.getenv(name) or "").strip()
        if value:
            return value

    return None


def is_huggingface_url(url):
    """True only for Hugging Face hosts, so the token is never sent anywhere else"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False

    return any(host == h or host.endswith("." + h) for h in _HF_HOSTS)


def hf_auth_args(url, explicit_token=None):
    """aria2c args that authenticate a Hugging Face download, or [] when not applicable"""
    token = get_hf_token(explicit_token)

    if not token or not is_huggingface_url(url):
        return []

    return ["--header=Authorization: Bearer " + token]


def redact_token(text, explicit_token=None):
    """Strip any token value out of text before it is logged or broadcast"""
    if not text:
        return text

    candidates = [explicit_token] + [os.getenv(name) for name in _TOKEN_ENV_VARS]

    for candidate in candidates:
        if candidate and candidate.strip():
            text = text.replace(candidate.strip(), "***")

    return text
