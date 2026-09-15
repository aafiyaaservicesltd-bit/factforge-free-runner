#!/usr/bin/env python3
"""One-job, zero-metered-API FactForge production runner."""

from __future__ import annotations

import hashlib
import html
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


FACTFORGE_URL = os.environ.get("FACTFORGE_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-lessac-medium")
PIPER_DATA_DIR = os.environ.get("PIPER_DATA_DIR", "")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")
USER_AGENT = (
    "FactForgeFreeRunner/1.0 "
    "(+https://github.com/aafiyaaservicesltd-bit/factforge-free-runner)"
)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
Image.MAX_IMAGE_PIXELS = 40_000_000

TOPICS = [
    "how bioluminescent bays glow",
    "why ancient Roman concrete lasts",
    "how migrating birds navigate",
    "giant sequoia fire adaptations",
    "the Antikythera mechanism",
    "the story of the Voyager Golden Record",
    "what ice cores reveal about ancient climates",
    "life around deep sea hydrothermal vents",
    "how basalt columns form",
    "the science of fog harvesting",
    "how desert varnish forms on rocks",
    "the hidden ecosystem inside caves",
    "how the first accurate marine chronometers worked",
    "the science behind singing sand dunes",
    "how tardigrades survive extreme conditions",
    "the engineering of ancient aqueducts",
    "how coral atolls form",
    "why some lakes turn pink",
    "the natural history of amber fossils",
    "how tree rings preserve environmental history",
    "the geometry of snow crystals",
    "how octopuses change color",
    "the origin of the metric system",
    "how lighthouses developed their unique signals",
    "the discovery of plate tectonics",
    "how paper was made in the ancient world",
    "the science of auroras",
    "how seed vaults preserve crop diversity",
    "why whale songs travel so far",
    "the story of the first deep ocean expeditions",
]

PROHIBITED = re.compile(
    r"\b(election|candidate|president|prime minister|political party|war footage|"
    r"mass shooting|suicide|murder case|true crime|medical advice|diagnosis|"
    r"treatment plan|legal advice|investment advice|stock pick|crypto pick|"
    r"celebrity scandal|sexual content|weapon tutorial)\b",
    re.IGNORECASE,
)
BLOCKED_HOSTS = {
    "reddit.com",
    "wikipedia.org",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "pinterest.com",
    "youtube.com",
}
PREFERRED_HOST_PARTS = (
    ".gov",
    ".edu",
    ".ac.uk",
    "nasa.gov",
    "noaa.gov",
    "usgs.gov",
    "si.edu",
    "smithsonian",
    "nature.com",
    "science.org",
    "britannica.com",
    "nationalgeographic.com",
    "royalsociety.org",
    "historymuseum",
    "museum",
    "observatory",
)


class FactForgeError(RuntimeError):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status = status


def require_environment() -> None:
    required = {
        "FACTFORGE_URL": FACTFORGE_URL,
        "ACTIONS_ID_TOKEN_REQUEST_URL": os.environ.get(
            "ACTIONS_ID_TOKEN_REQUEST_URL", ""
        ),
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": os.environ.get(
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""
        ),
        "PIPER_DATA_DIR": PIPER_DATA_DIR,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing runner environment: {', '.join(missing)}")


def github_oidc_token() -> str:
    response = requests.get(
        os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"],
        params={"audience": "factforge-ai"},
        headers={
            "Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"
        },
        timeout=20,
    )
    response.raise_for_status()
    token = response.json().get("value")
    if not isinstance(token, str) or token.count(".") != 2:
        raise RuntimeError("GitHub did not issue a usable OIDC identity token.")
    return token


def factforge_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    data: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    request_headers = {
        "Authorization": f"Bearer {github_oidc_token()}",
        "Accept": "application/json",
        "X-GitHub-Run-Id": RUN_ID,
        **(headers or {}),
    }
    response = SESSION.request(
        method,
        f"{FACTFORGE_URL}{path}",
        json=payload,
        data=data,
        headers=request_headers,
        timeout=(20, timeout),
    )
    try:
        result = response.json()
    except ValueError:
        result = {}
    if not response.ok:
        message = result.get("error") if isinstance(result, dict) else None
        raise FactForgeError(
            str(message or f"FactForge request failed with HTTP {response.status_code}."),
            response.status_code,
        )
    if not isinstance(result, dict):
        raise FactForgeError("FactForge returned an unexpected response.", 502)
    return result


def normalized_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def blocked_source(url: str) -> bool:
    parsed = urlparse(url)
    host = normalized_host(url)
    if parsed.scheme != "https" or not host or "." not in host:
        return True
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_HOSTS):
        return True
    return bool(
        re.search(
            r"\.(pdf|zip|jpg|jpeg|png|gif|svg|webp|mp3|mp4)(?:$|\?)",
            parsed.path,
            re.IGNORECASE,
        )
    )


def authority_rank(url: str) -> tuple[int, int]:
    host = normalized_host(url)
    preferred = any(part in host for part in PREFERRED_HOST_PARTS)
    return (0 if preferred else 1, len(url))


def wikipedia_candidates(topic: str) -> tuple[str, list[str]]:
    search = SESSION.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "list": "search",
            "srnamespace": 0,
            "srlimit": 5,
            "srsearch": topic,
        },
        timeout=20,
    )
    search.raise_for_status()
    rows = search.json().get("query", {}).get("search", [])
    if not rows:
        raise RuntimeError("Topic discovery returned no encyclopedia pages.")
    title = rows[0]["title"]
    page = SESSION.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "prop": "extracts|extlinks",
            "titles": title,
            "explaintext": 1,
            "exintro": 1,
            "ellimit": "max",
        },
        timeout=25,
    )
    page.raise_for_status()
    pages = page.json().get("query", {}).get("pages", {})
    record = next(iter(pages.values()), {})
    intro = str(record.get("extract", ""))
    links = [
        row.get("*")
        for row in record.get("extlinks", [])
        if isinstance(row, dict) and isinstance(row.get("*"), str)
    ]
    links = sorted({link for link in links if not blocked_source(link)}, key=authority_rank)
    return intro, links


def limited_html(url: str) -> tuple[str, str]:
    response = SESSION.get(url, timeout=20, stream=True, allow_redirects=True)
    response.raise_for_status()
    final_url = response.url
    if blocked_source(final_url):
        raise RuntimeError("Source redirected to an excluded address.")
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type:
        raise RuntimeError("Source did not return an HTML article.")
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(32_768):
        size += len(chunk)
        if size > 900_000:
            break
        chunks.append(chunk)
    encoding = response.encoding or "utf-8"
    return final_url, b"".join(chunks).decode(encoding, errors="replace")


def extract_source(url: str) -> dict[str, str]:
    final_url, raw = limited_html(url)
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup.select("script, style, nav, header, footer, form, aside"):
        node.decompose()
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())
    paragraphs = []
    for paragraph in soup.select("article p, main p, p"):
        value = " ".join(paragraph.get_text(" ", strip=True).split())
        if len(value) >= 70 and value not in paragraphs:
            paragraphs.append(value)
        if sum(map(len, paragraphs)) >= 7_000:
            break
    excerpt = "\n".join(paragraphs)
    if len(excerpt) < 700:
        raise RuntimeError("Source did not contain enough readable evidence.")
    if PROHIBITED.search(f"{title} {excerpt[:3_000]}"):
        raise RuntimeError("Source crossed the sensitive-topic gate.")
    host = normalized_host(final_url)
    publisher = host.split(".")[-2].replace("-", " ").title()
    return {
        "title": (title or host)[:300],
        "publisher": publisher[:160],
        "url": final_url,
        "excerpt": excerpt[:7_000],
    }


def discover_sources(job_id: str, focus: str) -> tuple[str, str, list[dict[str, str]]]:
    seed = int(hashlib.sha256(f"{job_id}:{RUN_ID}".encode()).hexdigest()[:12], 16)
    ordered_topics = TOPICS[:]
    random.Random(seed).shuffle(ordered_topics)
    if focus and focus.lower() not in {"interesting facts and stories", "general"}:
        ordered_topics.insert(0, focus[:120])

    last_error = "No topic passed the source gate."
    for topic in ordered_topics[:12]:
        if PROHIBITED.search(topic):
            continue
        try:
            intro, links = wikipedia_candidates(topic)
            sources: list[dict[str, str]] = []
            seen_hosts: set[str] = set()
            for link in links[:36]:
                try:
                    source = extract_source(link)
                except Exception as error:  # A single publisher must not stop discovery.
                    last_error = str(error)
                    continue
                host = normalized_host(source["url"])
                if host in seen_hosts:
                    continue
                sources.append(source)
                seen_hosts.add(host)
                if len(sources) == 3:
                    break
            if len(sources) >= 2:
                return topic, intro[:2_500], sources
        except Exception as error:
            last_error = str(error)
    raise RuntimeError(f"Two independent readable sources were not found: {last_error}")


def distribute_duration(total: int, count: int) -> list[int]:
    base, remainder = divmod(total, count)
    values = [base + (1 if index < remainder else 0) for index in range(count)]
    if min(values) < 2 or max(values) > 55:
        raise RuntimeError("Requested video length cannot fit the guarded scene limits.")
    return values


def model_json(prompt: str, max_tokens: int) -> dict[str, Any]:
    response = SESSION.post(
        "http://127.0.0.1:11434/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 16_384,
                "num_predict": max_tokens,
                "repeat_penalty": 1.08,
            },
        },
        timeout=(20, 900),
    )
    response.raise_for_status()
    text = str(response.json().get("response", "")).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("The local model did not return JSON.")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("The local model did not return a content object.")
    return value


def normalize_content_pack(
    raw: dict[str, Any],
    *,
    topic: str,
    sources: list[dict[str, str]],
    durations: list[int],
    video_format: str,
) -> dict[str, Any]:
    title = str(raw.get("title", "")).strip()
    description = str(raw.get("description", "")).strip()
    hook = str(raw.get("hook", "")).strip()
    if not (8 <= len(title) <= 100) or len(description) < 20 or len(hook) < 3:
        raise RuntimeError("Title, hook, or description was incomplete.")
    if PROHIBITED.search(f"{title} {topic} {description}"):
        raise RuntimeError("The local draft crossed the sensitive-topic gate.")

    source_records = [
        {key: source[key] for key in ("title", "publisher", "url")} for source in sources
    ]
    allowed_urls = {source["url"] for source in source_records}
    claims = raw.get("claims")
    if not isinstance(claims, list) or not claims:
        raise RuntimeError("The local draft supplied no mapped fact claims.")
    normalized_claims = []
    for claim in claims[:40]:
        if not isinstance(claim, dict):
            raise RuntimeError("A fact claim was malformed.")
        text = str(claim.get("claim", "")).strip()
        confidence = claim.get("confidence")
        urls = claim.get("sourceUrls")
        if (
            len(text) < 3
            or not isinstance(confidence, (int, float))
            or not 0.82 <= float(confidence) <= 1
            or not isinstance(urls, list)
            or not urls
            or any(url not in allowed_urls for url in urls)
        ):
            raise RuntimeError("A fact claim failed its evidence mapping.")
        normalized_claims.append(
            {
                "claim": text[:1_000],
                "confidence": float(confidence),
                "sourceUrls": list(dict.fromkeys(urls))[:12],
            }
        )

    scenes = raw.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(durations):
        raise RuntimeError("The local draft returned the wrong scene count.")
    normalized_scenes = []
    for index, (scene, duration) in enumerate(zip(scenes, durations, strict=True)):
        if not isinstance(scene, dict):
            raise RuntimeError("A storyboard scene was malformed.")
        narration = str(scene.get("narration", "")).strip()
        on_screen = str(scene.get("onScreenText", "")).strip()
        visual = str(scene.get("visualPrompt", "")).strip()
        word_count = len(narration.split())
        max_words = 34 if video_format == "short" else 125
        if (
            not narration
            or not on_screen
            or not visual
            or word_count < 7
            or word_count > max_words
        ):
            raise RuntimeError(f"Scene {index + 1} failed the narration limits.")
        if PROHIBITED.search(f"{narration} {on_screen} {visual}"):
            raise RuntimeError("A storyboard scene crossed the sensitive-topic gate.")
        normalized_scenes.append(
            {
                "narration": narration[:4_000],
                "onScreenText": on_screen[:240],
                "visualPrompt": visual[:500],
                "durationSeconds": duration,
            }
        )

    tags = raw.get("tags")
    if not isinstance(tags, list):
        tags = []
    clean_tags = [
        re.sub(r"^#", "", str(tag)).strip()[:80]
        for tag in tags
        if str(tag).strip()
    ][:15]
    if not clean_tags:
        clean_tags = ["InterestingFacts", "Learning", "FactForgeAI"]
    return {
        "title": title,
        "topic": topic,
        "hook": hook[:500],
        "description": description[:4_000],
        "tags": clean_tags,
        "disclosure": (
            "This video uses AI-assisted research, public-domain or original visuals, "
            "and a synthetic narration voice. Sources were checked before publishing."
        ),
        "sources": source_records,
        "claims": normalized_claims,
        "scenes": normalized_scenes,
    }


def generate_content_pack(job: dict[str, Any]) -> dict[str, Any]:
    video_format = str(job["format"])
    scene_count = 6 if video_format == "short" else 12
    requested = int(job.get("targetLengthSeconds", 45 if video_format == "short" else 420))
    total_seconds = (
        max(32, min(58, requested))
        if video_format == "short"
        else max(300, min(540, requested))
    )
    durations = distribute_duration(total_seconds, scene_count)
    topic, encyclopedia_intro, sources = discover_sources(
        str(job["id"]), str(job.get("focus", ""))
    )
    source_bundle = [
        {
            "title": source["title"],
            "publisher": source["publisher"],
            "url": source["url"],
            "excerpt": source["excerpt"],
        }
        for source in sources
    ]
    narration_words = "14-24" if video_format == "short" else "65-95"
    prompt = f"""
You are the careful writer for an educational YouTube channel. Create an original,
engaging {video_format} story about {topic}. Use only facts supported by the source
excerpts below. Do not quote or closely imitate the prose. Do not invent dates,
numbers, names, or causal claims. Avoid politics, conflict, tragedy, crime, medical,
legal, financial, celebrity, sexual, child-directed, or dangerous material.

Return one JSON object only with these keys:
- title: 8-100 characters
- hook: one sharp opening sentence
- description: 2-4 original sentences
- tags: 5-10 strings without #
- claims: 5-12 objects with claim, confidence (0.82-1.0), and sourceUrls. Every URL
  must be copied exactly from the supplied sources and genuinely support that claim.
- scenes: exactly {scene_count} objects with narration, onScreenText, visualPrompt.
  Each narration must be {narration_words} words, onScreenText at most 8 words, and
  visualPrompt must describe a rights-safe documentary image without people, logos,
  brands, copyrighted characters, or text.

The fixed scene durations in seconds are {durations}. Build a complete narrative arc:
hook, context, evidence, explanation, surprising implication, and a satisfying ending.

Encyclopedia discovery summary (not an allowed citation):
{encyclopedia_intro}

Allowed source evidence:
{json.dumps(source_bundle, ensure_ascii=False)}
""".strip()

    last_error = "The local model did not complete a valid draft."
    for attempt in range(3):
        attempt_prompt = prompt
        if attempt:
            attempt_prompt += (
                "\n\nYour previous draft failed this exact structural check: "
                f"{last_error}. Return a fully corrected JSON object."
            )
        try:
            raw = model_json(attempt_prompt, 4_000 if video_format == "short" else 7_500)
            return normalize_content_pack(
                raw,
                topic=topic,
                sources=sources,
                durations=durations,
                video_format=video_format,
            )
        except Exception as error:
            last_error = str(error)[:300]
    raise RuntimeError(last_error)


def plain_text(value: str) -> str:
    return " ".join(BeautifulSoup(html.unescape(value), "html.parser").get_text(" ").split())


def commons_images(query: str, limit: int) -> list[str]:
    response = SESSION.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrlimit": min(40, max(12, limit * 3)),
            "gsrsearch": f"{query} filetype:bitmap",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 1600,
        },
        timeout=25,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    urls: list[str] = []
    for page in pages.values():
        info_rows = page.get("imageinfo", []) if isinstance(page, dict) else []
        if not info_rows:
            continue
        info = info_rows[0]
        metadata = info.get("extmetadata", {})
        license_name = plain_text(str(metadata.get("LicenseShortName", {}).get("value", ""))).lower()
        usage_terms = plain_text(str(metadata.get("UsageTerms", {}).get("value", ""))).lower()
        if "cc0" not in license_name and "public domain" not in f"{license_name} {usage_terms}":
            continue
        candidate = info.get("thumburl") or info.get("url")
        if not isinstance(candidate, str) or not candidate.startswith("https://"):
            continue
        if not normalized_host(candidate).endswith("wikimedia.org"):
            continue
        urls.append(candidate)
        if len(urls) >= limit:
            break
    return urls


def attach_rights_safe_images(pack: dict[str, Any]) -> None:
    scenes = pack["scenes"]
    try:
        candidates = commons_images(str(pack["topic"]), len(scenes))
    except Exception:
        candidates = []
    used: set[str] = set()
    for index, scene in enumerate(scenes):
        candidate = next((url for url in candidates if url not in used), None)
        if candidate:
            scene["imageUrl"] = candidate
            used.add(candidate)
            continue
        if index < 4:
            try:
                extras = commons_images(str(scene["visualPrompt"]), 2)
            except Exception:
                extras = []
            candidate = next((url for url in extras if url not in used), None)
            if candidate:
                scene["imageUrl"] = candidate
                used.add(candidate)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = f"/usr/share/fonts/truetype/dejavu/{name}"
    return ImageFont.truetype(path, size=size)


def wrapped_lines(
    draw: ImageDraw.ImageDraw,
    value: str,
    face: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=face)[2]
        if current and width > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:5]


def download_image(url: str, destination: Path) -> bool:
    try:
        response = SESSION.get(url, timeout=30, stream=True)
        response.raise_for_status()
        length = int(response.headers.get("content-length", "0") or 0)
        if length and length > 14 * 1024 * 1024:
            return False
        received = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(65_536):
                received += len(chunk)
                if received > 14 * 1024 * 1024:
                    return False
                handle.write(chunk)
        with Image.open(destination) as image:
            image.verify()
        return True
    except Exception:
        destination.unlink(missing_ok=True)
        return False


def gradient_canvas(width: int, height: int, seed: int) -> Image.Image:
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    colors = [
        ((5, 20, 35), (13, 65, 78)),
        ((16, 13, 46), (64, 29, 91)),
        ((7, 32, 39), (17, 89, 76)),
        ((27, 19, 14), (93, 60, 24)),
    ]
    start, end = colors[seed % len(colors)]
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(start, end, strict=True))
        draw.line((0, y, width, y), fill=color)
    return image


def build_slide(
    scene: dict[str, Any],
    title: str,
    index: int,
    total: int,
    dimensions: tuple[int, int],
    work: Path,
) -> Path:
    width, height = dimensions
    raw_path = work / f"source-{index:02d}.img"
    source_url = scene.get("imageUrl")
    has_source = isinstance(source_url, str) and download_image(source_url, raw_path)
    if has_source:
        with Image.open(raw_path) as raw:
            base = ImageOps.fit(ImageOps.exif_transpose(raw).convert("RGB"), dimensions)
        base = ImageEnhance.Color(base).enhance(0.82)
        overlay = Image.new("RGBA", dimensions, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle((0, 0, width, height), fill=(2, 7, 18, 82))
        overlay_draw.rectangle((0, height * 0.52, width, height), fill=(2, 7, 18, 168))
        base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    else:
        base = gradient_canvas(width, height, index)

    draw = ImageDraw.Draw(base)
    margin = max(42, round(width * 0.065))
    accent = (95, 229, 255)
    muted = (190, 205, 224)
    headline_size = max(38, round(width * (0.065 if width > height else 0.082)))
    headline_font = font(headline_size, bold=True)
    small_font = font(max(18, round(width * 0.022)))
    badge_font = font(max(16, round(width * 0.018)), bold=True)
    lines = wrapped_lines(
        draw, str(scene["onScreenText"]), headline_font, width - margin * 2
    )
    line_height = round(headline_size * 1.18)
    block_height = len(lines) * line_height
    top = round(height * 0.58) - block_height // 2
    draw.rounded_rectangle(
        (margin - 18, top - 24, width - margin + 18, top + block_height + 28),
        radius=24,
        fill=(2, 8, 18, 178),
        outline=(95, 229, 255, 65),
        width=2,
    )
    for line_index, line in enumerate(lines):
        box = draw.textbbox((0, 0), line, font=headline_font)
        x = (width - (box[2] - box[0])) // 2
        draw.text((x, top + line_index * line_height), line, font=headline_font, fill="white")

    badge = "PUBLIC DOMAIN / CC0" if has_source else "ORIGINAL FACTFORGE SLIDE"
    draw.rounded_rectangle(
        (margin, margin, margin + draw.textlength(badge, font=badge_font) + 30, margin + 38),
        radius=18,
        fill=(4, 17, 30),
        outline=accent,
        width=1,
    )
    draw.text((margin + 15, margin + 8), badge, font=badge_font, fill=accent)
    footer = f"{title[:72]}   •   {index + 1}/{total}"
    draw.text((margin, height - margin - 28), footer, font=small_font, fill=muted)
    output = work / f"slide-{index:02d}.png"
    base.save(output, format="PNG", optimize=True)
    raw_path.unlink(missing_ok=True)
    return output


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / float(audio.getframerate())


def atempo_chain(value: float) -> str:
    factors: list[float] = []
    while value > 2:
        factors.append(2.0)
        value /= 2
    factors.append(max(1.0, value))
    return ",".join(f"atempo={factor:.5f}" for factor in factors)


def run(command: list[str], timeout: int = 600) -> None:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if completed.returncode:
        tail = completed.stdout[-1_500:].replace("\n", " ")
        raise RuntimeError(f"Local media command failed: {tail}")


def synthesize_scene(text: str, output: Path) -> None:
    run(
        [
            sys.executable,
            "-m",
            "piper",
            "-m",
            PIPER_VOICE,
            "--data-dir",
            PIPER_DATA_DIR,
            "-f",
            str(output),
            "--",
            text,
        ],
        timeout=180,
    )


def render_video(pack: dict[str, Any], video_format: str, work: Path) -> Path:
    dimensions = (720, 1280) if video_format == "short" else (1280, 720)
    width, height = dimensions
    scene_files: list[Path] = []
    for index, scene in enumerate(pack["scenes"]):
        slide = build_slide(
            scene, str(pack["title"]), index, len(pack["scenes"]), dimensions, work
        )
        audio = work / f"voice-{index:02d}.wav"
        synthesize_scene(str(scene["narration"]), audio)
        target = int(scene["durationSeconds"])
        audio_length = wav_seconds(audio)
        tempo = max(1.0, audio_length / max(1.0, target - 0.25))
        audio_filter = f"{atempo_chain(tempo)},apad=pad_dur={target}"
        scene_file = work / f"scene-{index:02d}.mp4"
        video_filter = (
            "zoompan=z='min(zoom+0.00035,1.055)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps=30,format=yuv420p"
        )
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                str(slide),
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                video_filter,
                "-af",
                audio_filter,
                "-t",
                str(target),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "27",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(scene_file),
            ],
            timeout=300,
        )
        scene_files.append(scene_file)

    concat = work / "scenes.txt"
    concat.write_text(
        "\n".join(f"file '{path.name}'" for path in scene_files) + "\n",
        encoding="utf-8",
    )
    output = work / "factforge.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ],
        timeout=300,
    )
    size = output.stat().st_size
    if size < 20_000 or size > 95 * 1024 * 1024:
        raise RuntimeError("The finished MP4 fell outside the upload size limit.")
    return output


def upload_video(job_id: str, path: Path) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    size = path.stat().st_size
    with path.open("rb") as handle:
        factforge_request(
            "PUT",
            f"/api/free-runner/jobs/{job_id}/video",
            data=handle,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "X-Content-Sha256": digest.hexdigest(),
            },
            timeout=900,
        )


def report_failure(job_id: str, error: Exception) -> None:
    message = re.sub(r"[\r\n\t]+", " ", str(error)).strip()[:600]
    try:
        factforge_request(
            "POST",
            f"/api/free-runner/jobs/{job_id}/fail",
            payload={"error": message or "The free runner stopped unexpectedly."},
        )
    except Exception as report_error:
        print(f"Could not report the stopped job: {report_error}", file=sys.stderr)


def main() -> int:
    require_environment()
    factforge_request("POST", "/api/free-runner/heartbeat")
    claim = factforge_request("POST", "/api/free-runner/claim")
    job = claim.get("job")
    if not isinstance(job, dict):
        print("No production job is due. The heartbeat is healthy.")
        return 0

    job_id = str(job.get("id", ""))
    action = str(job.get("action", ""))
    if not job_id:
        raise RuntimeError("FactForge returned a job without an identifier.")
    print(f"Claimed {job_id} for {action}.")
    try:
        if action == "publish":
            factforge_request(
                "POST", f"/api/free-runner/jobs/{job_id}/publish", timeout=900
            )
            print("YouTube accepted the staged video.")
            return 0

        if action == "create":
            pack = generate_content_pack(job)
            attach_rights_safe_images(pack)
            factforge_request(
                "POST",
                f"/api/free-runner/jobs/{job_id}/metadata",
                payload={"pack": pack},
                timeout=120,
            )
        elif action == "render" and isinstance(job.get("pack"), dict):
            pack = job["pack"]
        else:
            raise RuntimeError("FactForge returned an unsupported runner action.")

        with tempfile.TemporaryDirectory(prefix="factforge-") as temporary:
            mp4 = render_video(pack, str(job["format"]), Path(temporary))
            upload_video(job_id, mp4)
        factforge_request(
            "POST", f"/api/free-runner/jobs/{job_id}/publish", timeout=900
        )
        print("Production completed and YouTube accepted the upload.")
        return 0
    except FactForgeError as error:
        if error.status == 409 and "paused" in str(error).lower():
            print("Autopilot was paused during the run; the staged MP4 was preserved.")
            return 0
        report_failure(job_id, error)
        raise
    except Exception as error:
        report_failure(job_id, error)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FactForge free runner failed: {error}", file=sys.stderr)
        raise
