"""Generate automation scripts for Platform9 PCD and OpenStack operations."""

from __future__ import annotations

import logging

import anthropic
import html2text
import httpx

log = logging.getLogger(__name__)

API_REFERENCE_URLS: list[str] = [
    "https://docs.platform9.com/api-docs",
    "https://docs.openstack.org/api-ref/compute/",
    "https://docs.openstack.org/api-ref/network/v2/",
    "https://docs.openstack.org/api-ref/block-storage/v3/",
    "https://docs.openstack.org/api-ref/identity/v3/",
]

# Keyword → URL index mapping for relevance selection
_KEYWORD_URL_MAP: dict[str, int] = {
    "compute": 1,
    "nova": 1,
    "server": 1,
    "vm": 1,
    "instance": 1,
    "network": 2,
    "neutron": 2,
    "subnet": 2,
    "router": 2,
    "storage": 3,
    "cinder": 3,
    "volume": 3,
    "block": 3,
    "identity": 4,
    "keystone": 4,
    "token": 4,
    "auth": 4,
}

_MAX_URL_CHARS = 4000


def _select_api_urls(task: str) -> list[str]:
    """Return 2 most relevant API reference URLs based on keywords in *task*."""
    task_lower = task.lower()
    scores: dict[int, int] = {}
    for keyword, idx in _KEYWORD_URL_MAP.items():
        if keyword in task_lower:
            scores[idx] = scores.get(idx, 0) + 1

    if not scores:
        # Default: Platform9 API docs + compute
        return [API_REFERENCE_URLS[0], API_REFERENCE_URLS[1]]

    sorted_indices = sorted(scores, key=lambda i: scores[i], reverse=True)
    selected = [API_REFERENCE_URLS[i] for i in sorted_indices[:2]]
    # Always include pf9 api-docs as first entry if not already present
    if API_REFERENCE_URLS[0] not in selected:
        selected = [API_REFERENCE_URLS[0], selected[0]]
    return selected[:2]


def _fetch_url(url: str) -> str:
    """Fetch *url* and return truncated Markdown text."""
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return ""
    except Exception as exc:
        log.warning("Unexpected error fetching %s: %s", url, exc)
        return ""

    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    md = converter.handle(html)
    return md[:_MAX_URL_CHARS]


def build_automation(
    task: str,
    language: str = "python",
    local_docs: list[dict] | None = None,
) -> str:
    """
    Generate an automation script for a Platform9 PCD / OpenStack task.

    Args:
        task:       Natural-language description of what the script should do.
        language:   "python" or "bash".
        local_docs: Optional list of {"filename", "path", "text"} dicts.

    Returns:
        Generated code string.
    """
    urls = _select_api_urls(task)
    fetched: list[tuple[str, str]] = []
    for url in urls:
        log.info("Fetching API reference: %s", url)
        content = _fetch_url(url)
        if content:
            fetched.append((url, content))

    content_blocks: list[dict] = []

    if fetched:
        api_text = "\n\n".join(
            f"--- API Reference: {url} ---\n{text}" for url, text in fetched
        )
        content_blocks.append(
            {
                "type": "text",
                "text": f"API reference documentation:\n\n{api_text}",
                "cache_control": {"type": "ephemeral"},
            }
        )

    if local_docs:
        local_parts = [
            f"--- Local doc: {doc['filename']} ---\n{doc['text'][:3000]}"
            for doc in local_docs[:2]
        ]
        if local_parts:
            content_blocks.append(
                {
                    "type": "text",
                    "text": "Local reference documents:\n\n" + "\n\n".join(local_parts),
                }
            )

    content_blocks.append({"type": "text", "text": f"Task: {task}"})

    system_prompt = (
        f"You are a Platform9 PCD automation expert. Generate {language} code to {task}. "
        "Include: proper OpenStack authentication (keystoneauth1 for Python, curl for Bash), "
        "error handling, inline comments, a usage example at the top. "
        "Code must run against Platform9 PCD (OpenStack Epoxy+). "
        "Use environment variables for credentials: "
        "OS_AUTH_URL, OS_PROJECT_NAME, OS_USERNAME, OS_PASSWORD, OS_DOMAIN_NAME."
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": content_blocks}],
    )

    return response.content[0].text.strip()
