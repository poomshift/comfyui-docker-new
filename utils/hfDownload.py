import os
import re
import shutil
from urllib.parse import unquote, urlparse

from utils.hfAuth import get_hf_token

# https://huggingface.co/<repo>/resolve/<revision>/<path within the repo>
_RESOLVE_RE = re.compile(r"^/(?P<repo>.+?)/resolve/(?P<revision>[^/]+)/(?P<path>.+)$")

# Only the site itself serves repos; the CDN hosts it redirects to do not
_REPO_HOSTS = ("huggingface.co", "hf.co")

_REPO_TYPE_PREFIXES = {"datasets": "dataset", "spaces": "space"}


def parse_hf_url(url):
    """Split a Hugging Face resolve URL into the parts hf_hub_download needs.

    Returns None for anything else, including CDN links, which have to keep
    going through aria2c.
    """
    try:
        parts = urlparse(url)
    except ValueError:
        return None

    if (parts.hostname or "").lower() not in _REPO_HOSTS:
        return None

    match = _RESOLVE_RE.match(parts.path)
    if not match:
        return None

    repo = match.group("repo")
    repo_type = "model"

    head, _, rest = repo.partition("/")
    if head in _REPO_TYPE_PREFIXES and rest:
        repo_type = _REPO_TYPE_PREFIXES[head]
        repo = rest

    # A repo id is "name" or "org/name"; anything deeper is not one
    if repo.count("/") > 1:
        return None

    return {
        "repo_id": repo,
        "repo_type": repo_type,
        "revision": unquote(match.group("revision")),
        "path": unquote(match.group("path")),
    }


def hf_client_enabled():
    """Whether to route Hugging Face URLs through the official client."""
    return (os.getenv("USE_HF_XET", "true") or "").strip().lower() not in (
        "false",
        "0",
        "no",
    )


def download_via_hf(url, output_dir, filename, staging_root="/workspace/.hf_staging"):
    """Fetch one file with huggingface_hub, which uses Xet where the repo has it.

    Xet transfers content-defined chunks and reuses any it already holds, so a
    model that mostly overlaps one already downloaded costs only its differing
    chunks. aria2c talks to the plain LFS CDN and gets none of that.

    Blocking - call it from a thread. Returns the final path.
    """
    from huggingface_hub import hf_hub_download

    info = parse_hf_url(url)
    if info is None:
        raise ValueError(f"not a Hugging Face resolve URL: {url}")

    # Staged separately so the client's .cache metadata never lands in models/
    staging = os.path.join(staging_root, re.sub(r"[^\w.-]", "_", filename))
    os.makedirs(staging, exist_ok=True)

    try:
        staged_path = hf_hub_download(
            repo_id=info["repo_id"],
            repo_type=info["repo_type"],
            revision=info["revision"],
            filename=info["path"],
            local_dir=staging,
            token=get_hf_token(),
        )

        os.makedirs(output_dir, exist_ok=True)
        target = os.path.join(output_dir, filename)
        shutil.move(staged_path, target)
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)
