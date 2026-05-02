"""Answer Platform9 PCD technical questions using live docs and local reference material."""

from __future__ import annotations

import logging

import anthropic
import html2text
import httpx

log = logging.getLogger(__name__)

REFERENCE_URLS: dict[str, list[str]] = {
    "pcd": [
        "https://docs.platform9.com/private-cloud-director",
        "https://docs.platform9.com/private-cloud-director/getting-started/self-hosted",
    ],
    "kubernetes": [
        "https://docs.platform9.com/private-cloud-director/kubernetes-clusters/k8s-overview",
        "https://kubernetes.io/docs/home/",
    ],
    "troubleshoot": [
        "https://platform9.com/kb/pcd-ts",
        "https://platform9.com/kb/pcd",
    ],
    "openstack": [
        "https://docs.openstack.org/epoxy/",
        "https://docs.openstack.org/epoxy/admin/",
    ],
}

# Maximum characters to keep from each fetched page
_MAX_URL_CHARS = 4000
# Maximum local doc chars per doc and doc count
_MAX_LOCAL_DOC_CHARS = 3000
_MAX_LOCAL_DOCS = 2


def _select_urls(question: str) -> list[str]:
    """Pick at most 2 relevant URLs based on keywords present in the question."""
    q = question.lower()
    selected: list[str] = []
    for category, urls in REFERENCE_URLS.items():
        if category in q:
            selected.extend(urls)
        if len(selected) >= 2:
            break
    # Fallback to pcd category
    if not selected:
        selected = REFERENCE_URLS["pcd"]
    return selected[:2]


def _fetch_url(url: str) -> str:
    """Fetch *url* and return its content as Markdown text (truncated)."""
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
    converter.body_width = 0  # no line wrapping
    md = converter.handle(html)
    return md[:_MAX_URL_CHARS]


def answer_query(question: str, local_docs: list[dict] | None = None) -> str:
    """
    Answer a Platform9 PCD technical question.

    Fetches relevant web content, optionally includes local docs, then calls Claude.

    Args:
        question:   The technical question to answer.
        local_docs: Optional list of {"filename", "path", "text"} dicts from docs_reader.

    Returns:
        Claude's answer string, with citations appended.
    """
    urls = _select_urls(question)
    fetched: list[tuple[str, str]] = []
    for url in urls:
        log.info("Fetching %s", url)
        content = _fetch_url(url)
        if content:
            fetched.append((url, content))

    # Build message content blocks
    content_blocks: list[dict] = []

    if fetched:
        web_text = "\n\n".join(
            f"--- Source: {url} ---\n{text}" for url, text in fetched
        )
        content_blocks.append(
            {
                "type": "text",
                "text": f"Reference documentation from web:\n\n{web_text}",
                "cache_control": {"type": "ephemeral"},
            }
        )

    if local_docs:
        local_text_parts: list[str] = []
        for doc in local_docs[:_MAX_LOCAL_DOCS]:
            chunk = doc["text"][:_MAX_LOCAL_DOC_CHARS]
            local_text_parts.append(f"--- Local doc: {doc['filename']} ---\n{chunk}")
        if local_text_parts:
            content_blocks.append(
                {
                    "type": "text",
                    "text": "Local reference documents:\n\n" + "\n\n".join(local_text_parts),
                }
            )

    content_blocks.append({"type": "text", "text": question})

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=(
            "You are a Platform9 PCD technical expert. Answer the question using the "
            "reference documentation provided. Be specific and accurate. "
            "If the docs don't cover the topic, say so clearly."
        ),
        messages=[{"role": "user", "content": content_blocks}],
    )

    answer = response.content[0].text.strip()

    # Append citations
    if fetched:
        citation_lines = ", ".join(url for url, _ in fetched)
        answer += f"\n\n**References:** {citation_lines}"

    return answer
