#!/usr/bin/env python3
"""One-job, zero-metered-API FactForge production runner."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageStat,
)


FACTFORGE_URL = os.environ.get("FACTFORGE_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-hfc_female-medium")
PIPER_DATA_DIR = os.environ.get("PIPER_DATA_DIR", "")
SADTALKER_DIR = Path(os.environ.get("SADTALKER_DIR", "/tmp/factforge-sadtalker"))
HOST_ANIMATOR = os.environ.get("HOST_ANIMATOR", "sadtalker").strip().lower()
PRESENTER_SEGMENT_SECONDS = max(
    1.5, min(3.0, float(os.environ.get("PRESENTER_SEGMENT_SECONDS", "2.5")))
)
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")
HOST_SHEET = Path(__file__).resolve().parent / "assets" / "factforge-host.webp"
USER_AGENT = (
    "FactForgeFreeRunner/1.0 "
    "(+https://github.com/aafiyaaservicesltd-bit/factforge-free-runner)"
)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
Image.MAX_IMAGE_PIXELS = 40_000_000

# Motion-comic episodes use original procedural artwork, so the same adult
# heroine can remain visually consistent without copying a real person or a
# copyrighted character. The older documentary profiles remain available for
# already-queued jobs, but new automatic jobs default to the comic profile.
VIDEO_PROFILES: list[dict[str, Any]] = [
    {
        "id": "mali-motion-comic",
        "kind": "comic",
        "topic": (
            "Mali's original Thai kitchen motion-comic adventures about "
            "basil, cooking, and everyday problem-solving"
        ),
        "focusTerms": (
            "comic",
            "motion comic",
            "mali",
            "original character",
            "animated story",
            "interesting facts",
        ),
        "sourceUrls": (
            "https://hot-thai-kitchen.com/pad-kra-pao-beef/",
            "https://www.foodandwine.com/pad-krapow-basil-stir-fry-7485308",
            "https://thewoksoflife.com/pad-kra-pao/",
        ),
        "visualVariants": (
            (
                "Mali, an adult Thai comic heroine with long dark hair and a teal apron, opens her Bangkok kitchen at sunrise",
                "Mali discovers that the basket of fresh holy basil is missing beside the waiting wok",
                "Mali follows a trail of basil leaves through the kitchen and studies the shelves for clues",
                "Mali finds the fallen basil basket beneath a market cart and carefully pulls it free",
                "Mali returns to the hot wok and stir-fries the rescued basil with a joyful sweep",
                "Mali serves the finished basil dish and smiles as the kitchen glows at sunset",
            ),
            (
                "Mali, an adult Thai comic heroine with long dark hair and a teal apron, accepts a busy lunch challenge in her Bangkok kitchen",
                "Mali lays out holy basil, chilli, garlic, and a waiting wok before the first order",
                "Mali spots one wilted bunch and selects the freshest basil leaves for the dish",
                "Mali sends the ingredients through the hot wok as bold comic motion lines fill the kitchen",
                "Mali folds in the basil at the final moment while steam curls above the wok",
                "Mali presents the finished lunch and marks the kitchen challenge complete",
            ),
            (
                "Mali, an adult Thai comic heroine with long dark hair and a teal apron, receives a basil delivery at her Bangkok doorway",
                "Mali compares the fragrant leaves with the ingredients arranged beside her wok",
                "Mali washes and sorts the basil while comic panels reveal each careful kitchen step",
                "Mali crushes garlic and chilli as the wok begins to glow with heat",
                "Mali adds the basil near the finish and tosses everything together in the wok",
                "Mali shares the completed dish and files the recipe in her comic kitchen journal",
            ),
        ),
        "factClaims": (
            "Pad kra pao is a Thai stir-fried dish whose defining herb is holy basil.",
            "The ingredients are cooked quickly in a hot wok, with basil added near the end.",
        ),
    },
    {
        "id": "bangkok-night-market",
        "kind": "live",
        "topic": "the foods and vendor craft of a Bangkok night market",
        "focusTerms": ("market", "street food", "night", "vendor"),
        "query": "10 Things to Eat at Rot Fai Night Market in Bangkok",
        "requiredTitleTerms": ("rot fai", "night market", "bangkok"),
        "clipStarts": (2.0, 16.0, 58.0, 70.0, 103.0, 121.0),
        "visuals": (
            "close-up introduction to food at Bangkok's Rot Fai night market",
            "a vendor lifting cooked noodles from a bowl",
            "hands preparing coconut-milk custard at a market stall",
            "a vendor handling mango sticky rice",
            "grilled seafood being finished at the stall",
            "a bright watermelon dessert served in its rind",
        ),
    },
    {
        "id": "thai-basil-wok",
        "kind": "live",
        "topic": "how a Bangkok street-food cook prepares Thai basil squid stir-fry",
        "focusTerms": (
            "cook",
            "cooking",
            "daily chores",
            "basil",
            "stir fry",
            "wok",
            "women",
        ),
        "query": "Thai Basil Squid Stir Fry with Fried Egg Bangkok Street Food 2016",
        "sourceUrls": (
            "https://hot-thai-kitchen.com/pad-kra-pao-beef/",
            "https://www.foodandwine.com/pad-krapow-basil-stir-fry-7485308",
            "https://www.streetsmartkitchen.com/authentic-thai-squid-recipe/",
            "https://thewoksoflife.com/pad-kra-pao/",
        ),
        "requiredTitleTerms": ("thai basil", "squid", "stir fry"),
        "clipStarts": (5.0, 25.0, 90.0, 120.0, 148.0, 180.0),
        "visuals": (
            "overhead view of a street-food wok before cooking begins",
            "a fried egg cooking in the hot wok",
            "fresh chilli, basil, vegetables, and squid entering the wok",
            "the cook rapidly stir-frying squid and vegetables",
            "the sauce reducing as the ingredients are folded together",
            "Thai basil squid served over rice with a fried egg",
        ),
    },
    {
        "id": "thai-siu-mai",
        "kind": "live",
        "topic": "how a Thai street-food vendor shapes and serves siu mai",
        "focusTerms": ("dumpling", "siu mai", "siumai", "shumai"),
        "query": "Thai street food Siumai How to Make Cantonese Dim Sum style Siu Mai",
        "requiredTitleTerms": ("thai street food", "siumai", "siu mai"),
        "clipStarts": (1.0, 14.0, 30.0, 48.0, 68.0, 92.0),
        "visuals": (
            "a Thai street-food vendor beginning a batch of siu mai",
            "the vendor portioning filling onto wrappers",
            "hands shaping individual siu mai dumplings",
            "the vendor repeating the shaping technique at speed",
            "finished siu mai arranged together on a banana leaf",
            "a serving of siu mai presented with dipping sauce",
        ),
    },
]

TOPICS = [
    str(profile["topic"])
    for profile in VIDEO_PROFILES
    if profile.get("kind") == "comic"
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
    ".ac.th",
    ".go.th",
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
    "tourismthailand.org",
    "bangkokpost.com",
    "unesco.org",
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


def topical_link_rank(topic: str, url: str) -> tuple[int, int, int, int]:
    blob = url.lower()
    terms = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z'-]+", topic)
        if len(word) >= 4
        and word.lower()
        not in {"everyday", "traditional", "preparing", "behind", "story"}
    ]
    if "thai" in terms or "thailand" in terms:
        terms.extend(["bangkok", "amphawa", "damnoen", "khlong"])
    hits = sum(term in blob for term in set(terms))
    authority, length = authority_rank(url)
    return (0 if hits else 1, authority, -hits, length)


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
    titles = [str(row["title"]) for row in rows if row.get("title")][:5]
    if not titles:
        raise RuntimeError("Topic discovery returned no usable encyclopedia pages.")
    page = SESSION.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "prop": "extracts|extlinks",
            "titles": "|".join(titles),
            "explaintext": 1,
            "exintro": 1,
            "ellimit": "max",
            "redirects": 1,
        },
        timeout=25,
    )
    page.raise_for_status()
    pages = page.json().get("query", {}).get("pages", {})
    records = [record for record in pages.values() if isinstance(record, dict)]
    records_by_title = {str(record.get("title", "")): record for record in records}
    intro_record = next(
        (records_by_title[title] for title in titles if title in records_by_title),
        records[0] if records else {},
    )
    intro = str(intro_record.get("extract", ""))
    links = []
    for record in records:
        links.extend(
            row.get("*")
            for row in record.get("extlinks", [])
            if isinstance(row, dict) and isinstance(row.get("*"), str)
        )
    links = sorted(
        {link for link in links if not blocked_source(link)},
        key=lambda link: topical_link_rank(topic, link),
    )
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


def source_relevant(topic: str, source: dict[str, str]) -> bool:
    haystack = f"{source['title']} {source['excerpt'][:4_000]}".lower()
    terms = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z'-]+", topic)
        if word.lower()
        not in {
            "a",
            "an",
            "and",
            "art",
            "behind",
            "day",
            "everyday",
            "how",
            "in",
            "of",
            "the",
            "traditional",
        }
        and len(word) >= 4
    ]
    terms = list(dict.fromkeys(terms))
    thai_topic = "thai" in terms or "thailand" in terms
    if thai_topic and not re.search(r"\bthai(?:land|land's)?\b", haystack):
        return False
    concept_terms = [term for term in terms if term not in {"thai", "thailand"}]
    hits = sum(bool(re.search(rf"\b{re.escape(term)}", haystack)) for term in concept_terms)
    return hits >= (1 if thai_topic else min(2, max(1, len(concept_terms))))


def video_profile_for_topic(topic: str) -> dict[str, Any] | None:
    lowered = topic.lower()
    for profile in VIDEO_PROFILES:
        if lowered == str(profile["topic"]).lower():
            return profile
    best: tuple[int, dict[str, Any]] | None = None
    for profile in VIDEO_PROFILES:
        score = sum(
            1
            for term in profile["focusTerms"]
            if str(term).lower() in lowered
        )
        if score and (best is None or score > best[0]):
            best = (score, profile)
    return best[1] if best else None


def video_profile_for_focus(focus: str) -> dict[str, Any]:
    lowered = focus.lower().strip()
    for profile in VIDEO_PROFILES:
        if lowered == str(profile["topic"]).lower():
            return profile
    if "motion-comic" in lowered or "mali's original" in lowered:
        return next(
            profile
            for profile in VIDEO_PROFILES
            if profile.get("kind") == "comic"
        )
    best: tuple[int, dict[str, Any]] | None = None
    for profile in VIDEO_PROFILES:
        score = sum(
            1
            for term in profile["focusTerms"]
            if str(term).lower() in lowered
        )
        if score and (best is None or score > best[0]):
            best = (score, profile)
    # The night-market profile has the widest range of visible actions and is
    # the safest default for a broad request such as "Thai food".
    return best[1] if best else VIDEO_PROFILES[0]


def profile_visual_plan(
    profile: dict[str, Any], count: int, variant_seed: int = 0
) -> list[str]:
    variants = profile.get("visualVariants")
    if isinstance(variants, tuple) and variants:
        selected = variants[variant_seed % len(variants)]
        visuals = [str(value) for value in selected]
    else:
        visuals = [str(value) for value in profile["visuals"]]
    if count == len(visuals):
        return visuals
    if profile.get("kind") == "comic" and count > len(visuals):
        angles = (
            "shown as a wide establishing comic panel",
            "shown as a close-up action comic panel",
        )
        return [
            (
                f"{visuals[min(len(visuals) - 1, index * len(visuals) // count)]}, "
                f"{angles[index % len(angles)]}"
            )
            for index in range(count)
        ]
    return [visuals[min(len(visuals) - 1, index * len(visuals) // count)] for index in range(count)]


def discover_sources(job_id: str, focus: str) -> tuple[str, str, list[dict[str, str]]]:
    seed = int(hashlib.sha256(f"{job_id}:{RUN_ID}".encode()).hexdigest()[:12], 16)
    selected_profile = video_profile_for_focus(focus)
    selected_topic = str(selected_profile["topic"])
    topic_locked = focus.strip().lower() == selected_topic.lower()
    remaining_topics = [topic for topic in TOPICS if topic != selected_topic]
    random.Random(seed).shuffle(remaining_topics)
    ordered_topics = [selected_topic] if topic_locked else [selected_topic, *remaining_topics]

    last_error = "No topic passed the source gate."
    for topic in ordered_topics[:12]:
        if PROHIBITED.search(topic):
            continue
        try:
            profile = video_profile_for_topic(topic)
            curated_links = list(profile.get("sourceUrls", ())) if profile else []
            try:
                intro, discovered_links = wikipedia_candidates(topic)
            except Exception:
                if not curated_links:
                    raise
                intro = (
                    "This story follows the visible cooking sequence in the inspected "
                    "street-food footage and uses the sources below for ingredient and "
                    "technique context."
                )
                discovered_links = []
            links = [*curated_links, *discovered_links]
            sources: list[dict[str, str]] = []
            seen_hosts: set[str] = set()
            for link in links[:36]:
                try:
                    source = extract_source(link)
                except Exception as error:  # A single publisher must not stop discovery.
                    last_error = str(error)
                    continue
                if not source_relevant(topic, source):
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
    visual_plan: list[str],
    profile: dict[str, Any],
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
    if profile.get("kind") == "comic":
        configured_claims = [
            str(value).strip()
            for value in profile.get("factClaims", ())
            if str(value).strip()
        ]
        claims = [
            {
                "claim": claim,
                "confidence": 0.9,
                "sourceUrls": [source_records[index % len(source_records)]["url"]],
            }
            for index, claim in enumerate(configured_claims)
        ]
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
        visual = visual_plan[index]
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
        visible_terms = {
            word.lower()
            for word in re.findall(r"[A-Za-z][A-Za-z'-]+", visual)
            if len(word) >= 4
            and word.lower()
            not in {
                "beginning",
                "bright",
                "close-up",
                "finished",
                "hands",
                "individual",
                "overhead",
                "rapidly",
                "served",
                "together",
                "vendor",
                "view",
            }
        }
        written_scene = f"{narration} {on_screen}".lower()
        if visible_terms and not any(term in written_scene for term in visible_terms):
            raise RuntimeError(
                f"Scene {index + 1} narration did not match its planned visual."
            )
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
            (
                "This is an original fictional motion comic starring an adult "
                "AI-designed character. Cultural and cooking details were checked "
                "against the listed sources, and narration uses a synthetic voice."
            )
            if profile.get("kind") == "comic"
            else (
                "This video uses AI-assisted research, an original AI presenter, "
                "Wikimedia Commons moving footage under the licenses listed in the "
                "description, and a synthetic narration voice. Sources were checked "
                "before publishing."
            )
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
    video_profile = video_profile_for_topic(topic)
    if not video_profile:
        raise RuntimeError("The selected topic had no supported production profile.")
    episode_seed = int(
        hashlib.sha256(str(job["id"]).encode()).hexdigest()[:12], 16
    )
    visual_plan = profile_visual_plan(video_profile, scene_count, episode_seed)
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
    comic_mode = video_profile.get("kind") == "comic"
    creative_direction = (
        """
Write an ORIGINAL motion-comic episode starring Mali, a fictional Thai woman in
her mid-twenties. Mali has long dark hair, a teal apron, a gold jasmine pin, a warm
personality, and practical intelligence. Keep this exact adult character identity
in every scene. Create a small kitchen mystery or challenge with a clear beginning,
turn, and satisfying payoff. The prose should sound warm and natural when spoken by
a female narrator, with simple conversational English and respectful Thai context.
The comic panels are already planned below, so every sentence must describe the
matching action. Never imitate, name, or resemble any existing franchise, celebrity,
real person, superhero, or copyrighted character.
"""
        if comic_mode
        else """
The moving footage is already selected. Every sentence must describe the matching
verified live action exactly; never mention a different ingredient or action.
"""
    )
    visual_label = (
        "Original chronological motion-comic panel plan"
        if comic_mode
        else "Verified chronological live-footage plan"
    )
    prompt = f"""
You are the careful writer for an educational YouTube channel. Create an original,
engaging {video_format} story about {topic}. Use only facts supported by the source
excerpts below. Do not quote or closely imitate the prose. Do not invent dates,
numbers, names, or causal claims. Avoid politics, conflict, tragedy, crime, medical,
legal, financial, celebrity, sexual, child-directed, or dangerous material.
{creative_direction}

Return one JSON object only with these keys:
- title: 8-100 characters
- hook: one sharp opening sentence
- description: 2-4 original sentences
- tags: 5-10 strings without #
- claims: 2-6 objects with claim, confidence (0.82-1.0), and sourceUrls. Every URL
  must be copied exactly from the supplied sources and genuinely support that claim.
- scenes: exactly {scene_count} objects with narration, onScreenText, visualPrompt.
  Each narration must be {narration_words} words, onScreenText at most 8 words, and
  visualPrompt must repeat the matching planned visual description below. Narration
  and on-screen text must describe what is genuinely shown in that exact panel.
  Adults may appear naturally in cooking, market, craft, or daily-life scenes, but
  never depict minors or sexualized people. Do not request logos, brands, copyrighted
  characters, or text.

The fixed scene durations in seconds are {durations}. Build a complete narrative arc:
hook, context, evidence, explanation, surprising implication, and a satisfying ending.

{visual_label} (one line per scene):
{chr(10).join(f"{index + 1}. {shot}" for index, shot in enumerate(visual_plan))}

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
            if comic_mode:
                raw_title = str(raw.get("title", "")).strip()
                if raw_title and "mali" not in raw_title.lower():
                    raw["title"] = f"Mali and {raw_title}"[:100]
            return normalize_content_pack(
                raw,
                topic=topic,
                sources=sources,
                durations=durations,
                video_format=video_format,
                visual_plan=visual_plan,
                profile=video_profile,
            )
        except Exception as error:
            last_error = str(error)[:300]
    raise RuntimeError(last_error)


def plain_text(value: str) -> str:
    decoded = html.unescape(value)
    if "<" in decoded and ">" in decoded:
        decoded = BeautifulSoup(decoded, "html.parser").get_text(" ")
    return " ".join(decoded.split())


def commons_license(metadata: dict[str, Any]) -> tuple[str, str] | None:
    license_name = plain_text(
        str(metadata.get("LicenseShortName", {}).get("value", ""))
    )
    usage_terms = plain_text(
        str(metadata.get("UsageTerms", {}).get("value", ""))
    )
    license_url = plain_text(
        str(metadata.get("LicenseUrl", {}).get("value", ""))
    )
    combined = f"{license_name} {usage_terms} {license_url}".lower()
    if "cc0" in combined:
        return (license_name or "CC0 1.0", "cc0")
    if "public domain" in combined or "publicdomain" in combined:
        return (license_name or "Public domain", "public-domain")
    excluded = (
        "by-sa",
        "by-nc",
        "by-nd",
        "share alike",
        "sharealike",
        "noncommercial",
        "non-commercial",
        "no derivatives",
        "noderivatives",
    )
    attribution_only = (
        "cc by" in combined
        or "creativecommons.org/licenses/by/" in combined
        or "creative commons attribution" in combined
    )
    if attribution_only and not any(term in combined for term in excluded):
        return (license_name or usage_terms or "CC BY", "cc-by")
    return None


def commons_images(query: str, limit: int) -> list[dict[str, str]]:
    response = SESSION.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrlimit": min(50, max(18, limit * 5)),
            "gsrsearch": f"filetype:bitmap {query[:120]}",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": 1600,
        },
        timeout=25,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    candidates: list[dict[str, str]] = []
    ordered_pages = sorted(
        (page for page in pages.values() if isinstance(page, dict)),
        key=lambda page: int(page.get("index", 1_000_000) or 1_000_000),
    )
    for page in ordered_pages:
        info_rows = page.get("imageinfo", []) if isinstance(page, dict) else []
        if not info_rows:
            continue
        info = info_rows[0]
        metadata = info.get("extmetadata", {})
        license_record = commons_license(metadata)
        mime = str(info.get("mime", "")).lower()
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        if (
            not license_record
            or mime not in {"image/jpeg", "image/png", "image/webp"}
            or min(width, height) < 600
        ):
            continue
        candidate = info.get("thumburl") or info.get("url")
        if not isinstance(candidate, str) or not candidate.startswith("https://"):
            continue
        if not normalized_host(candidate).endswith("wikimedia.org"):
            continue
        license_name, license_kind = license_record
        creator = plain_text(str(metadata.get("Artist", {}).get("value", "")))
        if license_kind == "cc-by" and not creator:
            continue
        if not creator:
            creator = "Wikimedia Commons contributor"
        source_url = str(info.get("descriptionurl", ""))
        if (
            not source_url.startswith("https://commons.wikimedia.org/")
            or len(source_url) > 2_000
        ):
            continue
        candidates.append(
            {
                "url": candidate,
                "creator": creator[:300],
                "license": license_name[:120],
                "sourceUrl": source_url,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def commons_videos(query: str, limit: int) -> list[dict[str, Any]]:
    response = SESSION.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrlimit": min(30, max(10, limit * 5)),
            "gsrsearch": f"filetype:video {query[:160]}",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
        },
        timeout=35,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    candidates: list[dict[str, Any]] = []
    ordered_pages = sorted(
        (page for page in pages.values() if isinstance(page, dict)),
        key=lambda page: int(page.get("index", 1_000_000) or 1_000_000),
    )
    for page in ordered_pages:
        info_rows = page.get("imageinfo", []) if isinstance(page, dict) else []
        if not info_rows:
            continue
        info = info_rows[0]
        metadata = info.get("extmetadata", {})
        license_record = commons_license(metadata)
        mime = str(info.get("mime", "")).lower()
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        duration = float(info.get("duration", 0) or 0)
        size = int(info.get("size", 0) or 0)
        if (
            not license_record
            or mime not in {"video/webm", "video/ogg", "application/ogg"}
            or min(width, height) < 480
            or duration < 20
            or not 0 < size <= 85 * 1024 * 1024
        ):
            continue
        candidate_url = info.get("url")
        if not isinstance(candidate_url, str) or not candidate_url.startswith("https://"):
            continue
        if not normalized_host(candidate_url).endswith("wikimedia.org"):
            continue
        license_name, license_kind = license_record
        creator = plain_text(str(metadata.get("Artist", {}).get("value", "")))
        if license_kind == "cc-by" and not creator:
            continue
        if not creator:
            creator = "Wikimedia Commons contributor"
        source_url = str(info.get("descriptionurl", ""))
        if (
            not source_url.startswith("https://commons.wikimedia.org/")
            or len(source_url) > 2_000
        ):
            continue
        title = plain_text(
            str(metadata.get("ObjectName", {}).get("value", page.get("title", "")))
        )
        description = plain_text(
            str(metadata.get("ImageDescription", {}).get("value", ""))
        )
        categories = plain_text(
            str(metadata.get("Categories", {}).get("value", "")).replace("|", " ")
        )
        candidates.append(
            {
                "url": candidate_url,
                "creator": creator[:300],
                "license": license_name[:120],
                "sourceUrl": source_url,
                "title": title[:500],
                "searchText": f"{title} {description} {categories}"[:4_000],
                "duration": duration,
                "size": size,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def candidate_matches_profile(
    candidate: dict[str, Any], profile: dict[str, Any]
) -> bool:
    haystack = str(candidate.get("searchText", candidate.get("title", ""))).lower()
    required = [str(term).lower() for term in profile["requiredTitleTerms"]]
    # Siumai has two common spellings, so one of those aliases is enough after
    # the distinctly Thai-street-food phrase has matched.
    if profile["id"] == "thai-siu-mai":
        return "thai street food" in haystack and any(
            alias in haystack for alias in ("siumai", "siu mai", "shumai")
        )
    return all(term in haystack for term in required)


def attach_rights_safe_videos(pack: dict[str, Any]) -> None:
    profile = video_profile_for_topic(str(pack["topic"]))
    if not profile:
        raise RuntimeError(
            "Live-footage gate stopped the upload: this topic has no inspected video plan."
        )
    if profile.get("kind") == "comic":
        for scene in pack["scenes"]:
            scene["_mediaMatch"] = str(profile["id"])
            scene["_renderStyle"] = "original-motion-comic"
            for key in (
                "imageUrl",
                "videoUrl",
                "mediaCreator",
                "mediaLicense",
                "mediaSourceUrl",
            ):
                scene.pop(key, None)
        print(
            "Original-art gate passed: every scene will use the consistent "
            "Mali motion-comic character model."
        )
        return
    try:
        candidates = commons_videos(str(profile["query"]), 8)
    except Exception as error:
        raise RuntimeError(
            "Live-footage gate could not verify the Wikimedia source."
        ) from error
    matching = [
        candidate
        for candidate in candidates
        if candidate_matches_profile(candidate, profile)
    ]
    if not matching:
        raise RuntimeError(
            "Live-footage gate stopped the upload: no license-safe video matched the story."
        )
    primary = matching[0]
    scenes = pack["scenes"]
    starts = [float(value) for value in profile["clipStarts"]]
    visual_plan = profile_visual_plan(profile, len(scenes))
    for index, scene in enumerate(scenes):
        start_index = min(len(starts) - 1, index * len(starts) // len(scenes))
        scene["visualPrompt"] = visual_plan[index]
        scene["videoUrl"] = primary["url"]
        scene["mediaCreator"] = primary["creator"]
        scene["mediaLicense"] = primary["license"]
        scene["mediaSourceUrl"] = primary["sourceUrl"]
        scene["_videoCandidates"] = matching
        scene["_clipStartSeconds"] = starts[start_index]
        scene["_mediaMatch"] = str(profile["id"])
    print(
        "Live-footage semantic gate passed: "
        f"{profile['id']} uses {primary['title']} for {len(scenes)} timed scenes."
    )


def image_search_terms(value: str, limit: int = 4) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]+", value)
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "for",
        "from",
        "how",
        "in",
        "is",
        "its",
        "day",
        "everyday",
        "story",
        "science",
        "traditional",
        "of",
        "on",
        "the",
        "to",
        "what",
        "why",
        "with",
    }
    useful = [word for word in words if word.lower() not in stop_words]
    return useful[:limit]


def image_search_queries(topic: str, scenes: list[dict[str, Any]]) -> list[str]:
    lowered = topic.lower()
    queries: list[str] = []
    if "thai" in lowered or "thailand" in lowered:
        if "floating market" in lowered:
            queries.extend(
                [
                    "Thailand floating market",
                    "Thailand market vendors",
                    "Thai food market",
                ]
            )
        elif "curry" in lowered:
            queries.extend(["Thai curry paste", "Thai cooking", "Thailand market spices"])
        elif "sticky rice" in lowered or "rice" in lowered:
            queries.extend(["Thai sticky rice", "Thai cooking", "Thailand food market"])
        elif "fruit" in lowered:
            queries.extend(["Thai fruit carving", "Thailand fruit market", "Thai artisans"])
        elif "weav" in lowered or "textile" in lowered:
            queries.extend(
                ["Thailand traditional weaving", "Thai textile artisans", "Thailand daily life"]
            )
        elif "market" in lowered:
            queries.extend(
                ["Thailand market vendors", "Thai food market", "Thailand daily life"]
            )
        else:
            queries.extend(["Thai cooking", "Thailand daily life", "Thailand market vendors"])

    topic_terms = image_search_terms(topic)
    if topic_terms:
        queries.append(" ".join(topic_terms))
        if len(topic_terms) > 2:
            queries.append(" ".join(topic_terms[-3:]))

    for scene in scenes[:4]:
        scene_terms = image_search_terms(
            f"{topic_terms[0] if topic_terms else ''} {scene.get('onScreenText', '')}",
            4,
        )
        if len(scene_terms) >= 2:
            queries.append(" ".join(scene_terms))

    return list(dict.fromkeys(query.strip() for query in queries if query.strip()))[:8]


def attach_rights_safe_images(pack: dict[str, Any]) -> None:
    scenes = pack["scenes"]
    target = len(scenes) * 3
    groups: list[list[dict[str, str]]] = []
    known_urls: set[str] = set()
    for query in image_search_queries(str(pack["topic"]), scenes):
        try:
            query_candidates = commons_images(query, min(18, len(scenes) * 2))
        except Exception:
            query_candidates = []
        group: list[dict[str, str]] = []
        for candidate in query_candidates:
            if candidate["url"] in known_urls:
                continue
            group.append(candidate)
            known_urls.add(candidate["url"])
        if group:
            groups.append(group)
        if len(known_urls) >= target:
            break

    candidates: list[dict[str, str]] = []
    for candidate_index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if candidate_index < len(group):
                candidates.append(group[candidate_index])

    print(
        f"Found {len(candidates)} rights-safe image candidates for "
        f"{len(scenes)} scenes."
    )
    if not candidates:
        return
    for index, scene in enumerate(scenes):
        ordered = candidates[index:] + candidates[:index]
        scene["_imageCandidates"] = ordered
        primary = ordered[0]
        scene["imageUrl"] = primary["url"]
        scene["mediaCreator"] = primary["creator"]
        scene["mediaLicense"] = primary["license"]
        scene["mediaSourceUrl"] = primary["sourceUrl"]


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


def download_video(url: str, destination: Path) -> bool:
    try:
        response = SESSION.get(url, timeout=(25, 240), stream=True)
        response.raise_for_status()
        length = int(response.headers.get("content-length", "0") or 0)
        if length and length > 85 * 1024 * 1024:
            return False
        received = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(256 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > 85 * 1024 * 1024:
                    destination.unlink(missing_ok=True)
                    return False
                handle.write(chunk)
        if received < 100_000:
            destination.unlink(missing_ok=True)
            return False
        duration = media_seconds(destination)
        if duration < 20:
            destination.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        destination.unlink(missing_ok=True)
        return False


def acquire_scene_video(
    scene: dict[str, Any],
    work: Path,
    cache: dict[str, Path],
) -> Path:
    stored_candidate = {
        "url": scene.get("videoUrl"),
        "creator": scene.get("mediaCreator"),
        "license": scene.get("mediaLicense"),
        "sourceUrl": scene.get("mediaSourceUrl"),
    }
    raw_candidates = scene.get("_videoCandidates", [])
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    if isinstance(stored_candidate["url"], str):
        candidates = [stored_candidate, *candidates]

    attempted: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_url = candidate.get("url")
        if not isinstance(source_url, str) or source_url in attempted:
            continue
        attempted.add(source_url)
        if source_url in cache:
            selected_path = cache[source_url]
        else:
            digest = hashlib.sha256(source_url.encode()).hexdigest()[:16]
            selected_path = work / f"live-source-{digest}.media"
            if not download_video(source_url, selected_path):
                continue
            cache[source_url] = selected_path
        scene["videoUrl"] = source_url
        scene["mediaCreator"] = str(
            candidate.get("creator", "Wikimedia Commons contributor")
        )
        scene["mediaLicense"] = str(candidate.get("license", ""))
        scene["mediaSourceUrl"] = str(candidate.get("sourceUrl", ""))
        scene["_sourceUsed"] = True
        return selected_path
    raise RuntimeError(
        "Live-footage gate stopped the upload: a verified scene video could not be downloaded."
    )


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
    rng = random.Random(seed * 97 + width + height)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for _ in range(7):
        radius = rng.randint(round(width * 0.12), round(width * 0.42))
        x = rng.randint(-radius, width)
        y = rng.randint(-radius, height)
        color = rng.choice(
            [
                (45, 212, 191, 54),
                (56, 189, 248, 46),
                (168, 85, 247, 42),
                (251, 191, 36, 34),
            ]
        )
        glow_draw.ellipse((x, y, x + radius * 2, y + radius * 2), fill=color)
    glow = glow.filter(ImageFilter.GaussianBlur(max(24, width // 18)))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    texture = ImageDraw.Draw(image)
    for offset in range(-height, width, max(90, width // 7)):
        texture.line(
            (offset, height, offset + height, 0),
            fill=(120, 220, 235),
            width=1,
        )
    return image


def documentary_canvas(raw: Image.Image, dimensions: tuple[int, int]) -> Image.Image:
    width, height = dimensions
    source = ImageOps.exif_transpose(raw).convert("RGB")
    source = ImageEnhance.Color(source).enhance(0.94)
    source = ImageEnhance.Contrast(source).enhance(1.06)
    source = ImageEnhance.Sharpness(source).enhance(1.12)
    source_ratio = source.width / max(1, source.height)
    canvas_ratio = width / max(1, height)
    if 0.72 <= source_ratio / canvas_ratio <= 1.38:
        return ImageOps.fit(source, dimensions, method=Image.Resampling.LANCZOS)

    background = ImageOps.fit(
        source, dimensions, method=Image.Resampling.LANCZOS
    ).filter(ImageFilter.GaussianBlur(max(18, width // 28)))
    background = ImageEnhance.Brightness(background).enhance(0.62)
    foreground_bounds = (
        round(width * 0.92),
        round(height * (0.66 if height > width else 0.78)),
    )
    foreground = ImageOps.contain(
        source, foreground_bounds, method=Image.Resampling.LANCZOS
    )
    x = (width - foreground.width) // 2
    y = round(height * 0.19) + max(0, (foreground_bounds[1] - foreground.height) // 2)
    mask = Image.new("L", foreground.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, foreground.width - 1, foreground.height - 1),
        radius=max(16, width // 35),
        fill=255,
    )
    background.paste(foreground, (x, y), mask)
    return background


def cinematic_overlay(dimensions: tuple[int, int]) -> Image.Image:
    width, height = dimensions
    overlay = Image.new("RGBA", dimensions, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top_span = max(1, round(height * 0.38))
    bottom_start = round(height * 0.62)
    for y in range(height):
        top_alpha = round(190 * max(0.0, 1 - y / top_span))
        bottom_alpha = round(
            175 * max(0.0, (y - bottom_start) / max(1, height - bottom_start))
        )
        alpha = max(top_alpha, bottom_alpha, 26)
        draw.line((0, y, width, y), fill=(2, 8, 18, alpha))
    return overlay


def host_pose(pose_index: int) -> Image.Image:
    """Return one transparent pose from the channel's original fictional host."""

    if not HOST_SHEET.exists():
        raise RuntimeError("The consistent FactForge host asset was missing.")
    crop_bounds = ((0.0, 0.384), (0.384, 0.676), (0.676, 1.0))
    with Image.open(HOST_SHEET) as sheet_raw:
        sheet = sheet_raw.convert("RGBA")
        left_ratio, right_ratio = crop_bounds[pose_index % len(crop_bounds)]
        pose = sheet.crop(
            (
                round(sheet.width * left_ratio),
                0,
                round(sheet.width * right_ratio),
                sheet.height,
            )
        )
    alpha_box = pose.getchannel("A").getbbox()
    if alpha_box:
        pose = pose.crop(alpha_box)
    return pose


def build_host_animation_source(output: Path) -> None:
    """Create a clean chroma-key source for the audio-driven presenter."""

    pose = host_pose(0)
    pose.thumbnail((474, 742), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (512, 768), (0, 255, 0))
    x = (canvas.width - pose.width) // 2
    y = canvas.height - pose.height
    canvas.paste(pose, (x, y), pose)
    canvas.save(output, format="PNG", optimize=True)


def build_slide(
    scene: dict[str, Any],
    title: str,
    index: int,
    total: int,
    dimensions: tuple[int, int],
    work: Path,
    used_sources: set[str],
) -> Path:
    width, height = dimensions
    raw_path = work / f"source-{index:02d}.img"
    stored_candidate = {
        "url": scene.get("imageUrl"),
        "creator": scene.get("mediaCreator"),
        "license": scene.get("mediaLicense"),
        "sourceUrl": scene.get("mediaSourceUrl"),
    }
    raw_candidates = scene.get("_imageCandidates", [])
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    if isinstance(stored_candidate["url"], str):
        candidates = [stored_candidate, *candidates]

    selected: dict[str, str] | None = None
    attempted: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_url = candidate.get("url")
        if (
            not isinstance(source_url, str)
            or source_url in attempted
            or source_url in used_sources
        ):
            continue
        attempted.add(source_url)
        if download_image(source_url, raw_path):
            selected = {
                "url": source_url,
                "creator": str(candidate.get("creator", "Wikimedia Commons contributor")),
                "license": str(candidate.get("license", "")),
                "sourceUrl": str(candidate.get("sourceUrl", "")),
            }
            used_sources.add(source_url)
            break

    has_source = selected is not None
    if has_source:
        with Image.open(raw_path) as raw:
            base = documentary_canvas(raw, dimensions)
        scene["imageUrl"] = selected["url"]
        scene["mediaCreator"] = selected["creator"]
        scene["mediaLicense"] = selected["license"]
        scene["mediaSourceUrl"] = selected["sourceUrl"]
    else:
        base = gradient_canvas(width, height, index)
        for key in ("imageUrl", "mediaCreator", "mediaLicense", "mediaSourceUrl"):
            scene.pop(key, None)
    scene["_sourceUsed"] = has_source

    base = Image.alpha_composite(
        base.convert("RGBA"), cinematic_overlay(dimensions)
    ).convert("RGB")

    draw = ImageDraw.Draw(base)
    margin = max(42, round(width * 0.065))
    accent = (95, 229, 255)
    muted = (208, 222, 238)
    headline_size = max(36, round(width * (0.045 if width > height else 0.064)))
    headline_font = font(headline_size, bold=True)
    small_font = font(max(17, round(width * 0.020)))
    brand_font = font(max(17, round(width * 0.020)), bold=True)
    lines = wrapped_lines(
        draw, str(scene["onScreenText"]), headline_font, width - margin * 2
    )[:3]
    line_height = round(headline_size * 1.15)
    block_height = len(lines) * line_height
    top = margin + max(68, round(height * 0.064))
    panel = Image.new("RGBA", dimensions, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rounded_rectangle(
        (margin - 20, top - 20, width - margin + 20, top + block_height + 24),
        radius=max(18, width // 42),
        fill=(2, 9, 20, 142),
        outline=(95, 229, 255, 52),
        width=2,
    )
    base = Image.alpha_composite(base.convert("RGBA"), panel).convert("RGB")
    draw = ImageDraw.Draw(base)
    for line_index, line in enumerate(lines):
        draw.text(
            (margin, top + line_index * line_height),
            line,
            font=headline_font,
            fill="white",
            stroke_width=max(1, width // 500),
            stroke_fill=(0, 0, 0),
        )

    brand = "FACTFORGE AI"
    counter = f"{index + 1:02d} / {total:02d}"
    draw.text((margin, margin), brand, font=brand_font, fill=accent)
    counter_width = draw.textbbox((0, 0), counter, font=small_font)[2]
    draw.text(
        (width - margin - counter_width, margin),
        counter,
        font=small_font,
        fill=muted,
    )
    line_y = margin + max(32, round(width * 0.038))
    draw.rounded_rectangle(
        (margin, line_y, width - margin, line_y + 4),
        radius=2,
        fill=(82, 108, 130),
    )
    progress_x = margin + round((width - margin * 2) * ((index + 1) / total))
    draw.rounded_rectangle(
        (margin, line_y, progress_x, line_y + 4),
        radius=2,
        fill=accent,
    )
    output = work / f"slide-{index:02d}.png"
    base.save(output, format="PNG", optimize=True)
    raw_path.unlink(missing_ok=True)
    return output


def build_live_overlay(
    scene: dict[str, Any],
    index: int,
    total: int,
    dimensions: tuple[int, int],
    work: Path,
) -> Path:
    width, height = dimensions
    overlay = cinematic_overlay(dimensions)
    draw = ImageDraw.Draw(overlay)
    margin = max(36, round(width * 0.055))
    accent = (95, 229, 255, 255)
    headline_size = max(30, round(width * (0.038 if width > height else 0.052)))
    headline_font = font(headline_size, bold=True)
    small_font = font(max(16, round(width * 0.020)))
    brand_font = font(max(17, round(width * 0.021)), bold=True)
    lines = wrapped_lines(
        draw,
        str(scene["onScreenText"]),
        headline_font,
        width - margin * 2,
    )[:2]
    line_height = round(headline_size * 1.12)
    top = margin + max(58, round(height * 0.05))
    block_height = max(line_height, len(lines) * line_height)
    draw.rounded_rectangle(
        (margin - 16, top - 14, width - margin + 16, top + block_height + 15),
        radius=max(16, width // 44),
        fill=(2, 9, 20, 142),
        outline=(95, 229, 255, 74),
        width=2,
    )
    for line_index, line in enumerate(lines):
        draw.text(
            (margin, top + line_index * line_height),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255),
            stroke_width=max(1, width // 520),
            stroke_fill=(0, 0, 0, 230),
        )

    draw.text((margin, margin), "FACTFORGE AI", font=brand_font, fill=accent)
    counter = f"{index + 1:02d} / {total:02d}"
    counter_width = draw.textbbox((0, 0), counter, font=small_font)[2]
    draw.text(
        (width - margin - counter_width, margin),
        counter,
        font=small_font,
        fill=(208, 222, 238, 255),
    )
    line_y = margin + max(30, round(width * 0.036))
    draw.rounded_rectangle(
        (margin, line_y, width - margin, line_y + 4),
        radius=2,
        fill=(82, 108, 130, 210),
    )
    progress_x = margin + round((width - margin * 2) * ((index + 1) / total))
    draw.rounded_rectangle(
        (margin, line_y, progress_x, line_y + 4),
        radius=2,
        fill=accent,
    )
    output = work / f"overlay-{index:02d}.png"
    overlay.save(output, format="PNG", optimize=True)
    return output


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / float(audio.getframerate())


def caption_chunks(value: str, max_words: int = 3) -> list[str]:
    words = value.split()
    if not words:
        return []
    count = max(1, (len(words) + max_words - 1) // max_words)
    base, remainder = divmod(len(words), count)
    chunks: list[str] = []
    cursor = 0
    for index in range(count):
        size = base + (1 if index < remainder else 0)
        chunks.append(" ".join(words[cursor : cursor + size]))
        cursor += size
    return chunks


def ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def write_captions(
    pack: dict[str, Any],
    output: Path,
    dimensions: tuple[int, int],
    video_format: str,
) -> None:
    width, height = dimensions
    comic_mode = bool(
        (video_profile_for_topic(str(pack.get("topic", ""))) or {}).get("kind")
        == "comic"
    )
    font_size = 38 if comic_mode and video_format == "short" else (36 if video_format == "short" else 34)
    margin_lr = 54 if video_format == "short" else 70
    margin_v = 86 if comic_mode and video_format == "short" else (260 if video_format == "short" else 58)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&HC0000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,{margin_lr},{margin_lr},{margin_v},1
Style: CaptionLeft,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&HC0000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,1,54,320,{margin_v},1
Style: CaptionRight,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&HC0000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,3,320,105,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    entries: list[str] = []
    timeline = 0.0
    for scene_index, scene in enumerate(pack["scenes"]):
        duration = float(scene["durationSeconds"])
        speech_duration = min(
            duration,
            max(0.6, float(scene.get("_speechDuration", duration))),
        )
        chunks = caption_chunks(str(scene["narration"]))
        caption_style = "Caption"
        if video_format == "short" and not comic_mode:
            caption_style = "CaptionLeft"
        available = max(0.5, speech_duration - 0.26)
        total_words = max(1, sum(len(chunk.split()) for chunk in chunks))
        position = timeline + 0.12
        for chunk_index, chunk in enumerate(chunks):
            share = available * len(chunk.split()) / total_words
            end = position + share
            if chunk_index == len(chunks) - 1:
                end = timeline + speech_duration - 0.08
            clean = re.sub(r"\s+", " ", chunk).strip()
            clean = clean.replace("{", "(").replace("}", ")")
            entries.append(
                f"Dialogue: 0,{ass_timestamp(position)},{ass_timestamp(end)},"
                f"{caption_style},,0,0,0,,{clean}"
            )
            position = end
        timeline += duration
    output.write_text(header + "\n".join(entries) + "\n", encoding="utf-8")


def atempo_chain(value: float) -> str:
    factors: list[float] = []
    while value > 2:
        factors.append(2.0)
        value /= 2
    factors.append(max(1.0, value))
    return ",".join(f"atempo={factor:.5f}" for factor in factors)


def run(
    command: list[str], timeout: int = 600, *, cwd: Path | None = None
) -> None:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
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


def presenter_timing(pack: dict[str, Any]) -> tuple[float, float, float]:
    durations = [float(scene["durationSeconds"]) for scene in pack["scenes"]]
    if len(durations) < 2:
        raise RuntimeError("The storyboard needs opening and closing presenter scenes.")
    # Real audio-driven animation is CPU-heavy. Two short presenter appearances
    # keep free hosted runners practical without falling back to a still image.
    intro = min(PRESENTER_SEGMENT_SECONDS, durations[0])
    outro = min(PRESENTER_SEGMENT_SECONDS, durations[-1])
    outro_start = sum(durations[:-1])
    return intro, outro_start, outro


def build_presenter_audio(
    assembled: Path, pack: dict[str, Any], output: Path
) -> tuple[float, float, float]:
    intro, outro_start, outro = presenter_timing(pack)
    audio_filter = (
        f"[0:a]atrim=start=0:end={intro:.3f},asetpts=PTS-STARTPTS[intro];"
        f"[0:a]atrim=start={outro_start:.3f}:"
        f"end={outro_start + outro:.3f},asetpts=PTS-STARTPTS[outro];"
        "[intro][outro]concat=n=2:v=0:a=1[presenter]"
    )
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(assembled),
            "-filter_complex",
            audio_filter,
            "-map",
            "[presenter]",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        timeout=180,
    )
    return intro, outro_start, outro


def media_seconds(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    try:
        duration = float(completed.stdout.strip())
    except ValueError as error:
        raise RuntimeError("The animated presenter duration could not be verified.") from error
    if completed.returncode or duration <= 0:
        raise RuntimeError("The animated presenter media was invalid.")
    return duration


def verify_host_motion(video: Path, work: Path) -> None:
    duration = media_seconds(video)
    moments = (0.6, min(2.4, max(0.8, duration * 0.45)), min(4.2, max(1.2, duration * 0.78)))
    frames: list[Path] = []
    for index, moment in enumerate(moments):
        frame = work / f"host-motion-{index}.png"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{moment:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(frame),
            ],
            timeout=90,
        )
        frames.append(frame)
    scores: list[float] = []
    with Image.open(frames[0]) as first_raw:
        first_frame = first_raw.convert("RGB")
        width, height = first_frame.size
        # The full-body chroma frame is mostly unchanged background and clothing.
        # Measure the centered head/face region where SadTalker actually moves.
        face_box = (
            round(width * 0.20),
            round(height * 0.15),
            round(width * 0.80),
            round(height * 0.52),
        )
        first = first_frame.crop(face_box)
        for frame in frames[1:]:
            with Image.open(frame) as other_raw:
                other_frame = other_raw.convert("RGB").resize(first_frame.size)
                other = other_frame.crop(face_box)
                difference = ImageChops.difference(first, other)
                scores.append(sum(ImageStat.Stat(difference).mean) / 3.0)
    motion_score = max(scores, default=0.0)
    if motion_score < 0.12:
        raise RuntimeError(
            "Presenter motion gate stopped the upload: the host animation was static "
            f"(face score {motion_score:.3f})."
        )
    print(f"Presenter motion gate passed with face score {motion_score:.3f}.")


def verify_scene_motion(
    video: Path, work: Path, scene_index: int, *, comic: bool = False
) -> None:
    duration = media_seconds(video)
    moments = (
        min(0.55, duration * 0.12),
        min(max(1.0, duration * 0.42), max(1.0, duration - 0.8)),
        min(max(1.4, duration * 0.78), max(1.4, duration - 0.25)),
    )
    frames: list[Path] = []
    for frame_index, moment in enumerate(moments):
        frame = work / f"scene-motion-{scene_index:02d}-{frame_index}.png"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{moment:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(frame),
            ],
            timeout=90,
        )
        frames.append(frame)
    scores: list[float] = []
    with Image.open(frames[0]) as first_raw:
        first_frame = first_raw.convert("RGB")
        width, height = first_frame.size
        action_box = (
            round(width * 0.08),
            round(height * 0.26),
            round(width * 0.92),
            round(height * 0.78),
        )
        first = first_frame.crop(action_box).resize((240, 240))
        for frame in frames[1:]:
            with Image.open(frame) as other_raw:
                other_frame = other_raw.convert("RGB").resize(first_frame.size)
                other = other_frame.crop(action_box).resize((240, 240))
                difference = ImageChops.difference(first, other)
                scores.append(sum(ImageStat.Stat(difference).mean) / 3.0)
    motion_score = max(scores, default=0.0)
    threshold = 0.22 if comic else 0.45
    if motion_score < threshold:
        raise RuntimeError(
            f"{'Motion-comic' if comic else 'Live-footage'} motion gate stopped the upload: "
            f"scene {scene_index + 1} was effectively static "
            f"(score {motion_score:.3f})."
        )
    print(
        f"{'Motion-comic' if comic else 'Live-footage'} motion gate passed for scene {scene_index + 1} "
        f"with score {motion_score:.3f}."
    )


def procedural_host_animation(audio: Path, source: Path, output: Path) -> None:
    """Fast local-only stand-in used to test the compositing pipeline."""

    duration = wav_seconds(audio)
    frames = max(1, round(duration * 30))
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
            str(source),
            "-i",
            str(audio),
            "-vf",
            (
                "zoompan=z='1.012+0.012*sin(on/19)':"
                "x='iw/2-(iw/zoom/2)+3*sin(on/13)':"
                "y='ih/2-(ih/zoom/2)+3*cos(on/17)':"
                f"d=1:s=512x768:fps=30,trim=end_frame={frames},format=yuv420p"
            ),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(output),
        ],
        timeout=420,
    )


def animate_presenter(audio: Path, work: Path) -> Path:
    source = work / "host-animation-source.png"
    build_host_animation_source(source)
    output = work / "animated-presenter.mp4"
    if HOST_ANIMATOR == "procedural":
        procedural_host_animation(audio, source, output)
    else:
        inference = SADTALKER_DIR / "inference.py"
        checkpoint = SADTALKER_DIR / "checkpoints"
        if not inference.exists() or not checkpoint.exists():
            raise RuntimeError(
                "The lifelike presenter engine was unavailable; no static-host video was uploaded."
            )
        result_dir = work / "presenter-results"
        result_dir.mkdir(parents=True, exist_ok=True)
        run(
            [
                sys.executable,
                str(inference),
                "--driven_audio",
                str(audio),
                "--source_image",
                str(source),
                "--checkpoint_dir",
                str(checkpoint),
                "--result_dir",
                str(result_dir),
                "--size",
                "256",
                "--preprocess",
                "full",
                "--pose_style",
                "4",
                "--expression_scale",
                "1.08",
                "--batch_size",
                "1",
                "--cpu",
            ],
            timeout=2_400,
            cwd=SADTALKER_DIR,
        )
        results = sorted(result_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime)
        if not results:
            raise RuntimeError("The lifelike presenter engine returned no video.")
        output.write_bytes(results[-1].read_bytes())
    expected = wav_seconds(audio)
    actual = media_seconds(output)
    if actual < expected - 1.2:
        raise RuntimeError("The animated presenter ended before the narration.")
    verify_host_motion(output, work)
    return output


def draw_comic_leaf(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    size: int,
    *,
    bright: bool = False,
) -> None:
    fill = (72, 181, 83) if bright else (37, 130, 72)
    outline = (11, 55, 42)
    draw.ellipse(
        (x - size, y - size // 2, x + size, y + size // 2),
        fill=fill,
        outline=outline,
        width=max(2, size // 7),
    )
    draw.line((x - size + 3, y, x + size - 3, y), fill=outline, width=2)


def draw_mali_character(
    canvas: Image.Image,
    *,
    center_x: int,
    foot_y: int,
    scale: float,
    frame_index: int,
    pose: int,
) -> None:
    """Draw the recurring fictional adult heroine with a stable visual model."""

    draw = ImageDraw.Draw(canvas)
    ink = (21, 22, 31)
    hair = (29, 24, 32)
    skin = (226, 170, 126)
    blush = (218, 108, 112)
    teal = (12, 128, 135)
    teal_light = (35, 179, 169)
    gold = (250, 194, 75)
    white = (250, 247, 238)

    def sx(value: float) -> int:
        return round(value * scale)

    bob = sx(math.sin(frame_index * math.pi / 4) * 3)
    cx = center_x
    fy = foot_y + bob
    torso_top = fy - sx(345)
    head_top = torso_top - sx(190)

    # Hair silhouette and long side locks.
    draw.ellipse(
        (
            cx - sx(112),
            head_top - sx(18),
            cx + sx(112),
            head_top + sx(218),
        ),
        fill=hair,
        outline=ink,
        width=sx(8),
    )
    draw.rounded_rectangle(
        (
            cx - sx(118),
            head_top + sx(105),
            cx - sx(52),
            torso_top + sx(210),
        ),
        radius=sx(28),
        fill=hair,
        outline=ink,
        width=sx(7),
    )
    draw.rounded_rectangle(
        (
            cx + sx(52),
            head_top + sx(105),
            cx + sx(118),
            torso_top + sx(210),
        ),
        radius=sx(28),
        fill=hair,
        outline=ink,
        width=sx(7),
    )

    # Neck, face, ears, and a side-swept fringe.
    draw.rounded_rectangle(
        (cx - sx(30), torso_top - sx(34), cx + sx(30), torso_top + sx(50)),
        radius=sx(16),
        fill=skin,
        outline=ink,
        width=sx(6),
    )
    draw.ellipse(
        (
            cx - sx(87),
            head_top + sx(20),
            cx + sx(87),
            head_top + sx(196),
        ),
        fill=skin,
        outline=ink,
        width=sx(7),
    )
    draw.pieslice(
        (
            cx - sx(104),
            head_top - sx(8),
            cx + sx(98),
            head_top + sx(132),
        ),
        180,
        350,
        fill=hair,
        outline=ink,
        width=sx(5),
    )
    draw.polygon(
        (
            (cx - sx(12), head_top + sx(10)),
            (cx + sx(86), head_top + sx(44)),
            (cx + sx(76), head_top + sx(98)),
        ),
        fill=hair,
    )

    blink = frame_index % 8 == 3
    eye_y = head_top + sx(105)
    for eye_x in (cx - sx(35), cx + sx(35)):
        if blink:
            draw.line(
                (eye_x - sx(12), eye_y, eye_x + sx(12), eye_y),
                fill=ink,
                width=sx(5),
            )
        else:
            draw.ellipse(
                (
                    eye_x - sx(13),
                    eye_y - sx(10),
                    eye_x + sx(13),
                    eye_y + sx(12),
                ),
                fill=white,
                outline=ink,
                width=sx(4),
            )
            draw.ellipse(
                (
                    eye_x - sx(4),
                    eye_y - sx(3),
                    eye_x + sx(5),
                    eye_y + sx(7),
                ),
                fill=ink,
            )
    draw.arc(
        (
            cx - sx(58),
            eye_y - sx(30),
            cx - sx(12),
            eye_y - sx(4),
        ),
        195,
        338,
        fill=ink,
        width=sx(5),
    )
    draw.arc(
        (
            cx + sx(12),
            eye_y - sx(30),
            cx + sx(58),
            eye_y - sx(4),
        ),
        202,
        345,
        fill=ink,
        width=sx(5),
    )
    draw.ellipse(
        (
            cx - sx(68),
            head_top + sx(134),
            cx - sx(42),
            head_top + sx(149),
        ),
        fill=blush,
    )
    draw.ellipse(
        (
            cx + sx(42),
            head_top + sx(134),
            cx + sx(68),
            head_top + sx(149),
        ),
        fill=blush,
    )
    if frame_index % 4 in (1, 2):
        draw.ellipse(
            (
                cx - sx(13),
                head_top + sx(148),
                cx + sx(13),
                head_top + sx(169),
            ),
            fill=(132, 49, 55),
            outline=ink,
            width=sx(3),
        )
    else:
        draw.arc(
            (
                cx - sx(25),
                head_top + sx(137),
                cx + sx(25),
                head_top + sx(174),
            ),
            10,
            170,
            fill=ink,
            width=sx(5),
        )

    # Teal blouse and apron make the character immediately recognizable.
    draw.polygon(
        (
            (cx - sx(95), torso_top + sx(32)),
            (cx - sx(155), fy - sx(36)),
            (cx + sx(155), fy - sx(36)),
            (cx + sx(95), torso_top + sx(32)),
        ),
        fill=teal,
        outline=ink,
    )
    draw.line(
        (
            cx - sx(95),
            torso_top + sx(32),
            cx - sx(155),
            fy - sx(36),
            cx + sx(155),
            fy - sx(36),
            cx + sx(95),
            torso_top + sx(32),
        ),
        fill=ink,
        width=sx(8),
        joint="curve",
    )
    draw.polygon(
        (
            (cx - sx(52), torso_top + sx(65)),
            (cx + sx(52), torso_top + sx(65)),
            (cx + sx(91), fy - sx(52)),
            (cx - sx(91), fy - sx(52)),
        ),
        fill=(235, 220, 190),
        outline=ink,
    )
    draw.line(
        (cx - sx(52), torso_top + sx(65), cx - sx(82), fy - sx(58)),
        fill=ink,
        width=sx(6),
    )
    draw.line(
        (cx + sx(52), torso_top + sx(65), cx + sx(82), fy - sx(58)),
        fill=ink,
        width=sx(6),
    )

    # Arms alternate between pointing, stirring, and presenting.
    arm_lift = sx(34 + 18 * math.sin((frame_index + pose) * math.pi / 4))
    left_hand = (cx - sx(172), torso_top + sx(148) - arm_lift)
    right_hand = (cx + sx(172), torso_top + sx(170) + arm_lift // 2)
    if pose % 3 == 1:
        right_hand = (cx + sx(206), torso_top + sx(68) - arm_lift)
    elif pose % 3 == 2:
        left_hand = (cx - sx(205), torso_top + sx(82) - arm_lift)
    for shoulder, hand in (
        ((cx - sx(82), torso_top + sx(82)), left_hand),
        ((cx + sx(82), torso_top + sx(82)), right_hand),
    ):
        draw.line((*shoulder, *hand), fill=ink, width=sx(34))
        draw.line((*shoulder, *hand), fill=teal_light, width=sx(22))
        draw.ellipse(
            (
                hand[0] - sx(18),
                hand[1] - sx(18),
                hand[0] + sx(18),
                hand[1] + sx(18),
            ),
            fill=skin,
            outline=ink,
            width=sx(5),
        )

    # Gold jasmine pin: a stable series marker.
    pin_x, pin_y = cx + sx(48), torso_top + sx(94)
    for angle in range(0, 360, 72):
        radians = math.radians(angle)
        px = pin_x + round(math.cos(radians) * sx(14))
        py = pin_y + round(math.sin(radians) * sx(14))
        draw.ellipse(
            (px - sx(7), py - sx(7), px + sx(7), py + sx(7)),
            fill=gold,
            outline=ink,
            width=sx(2),
        )
    draw.ellipse(
        (pin_x - sx(6), pin_y - sx(6), pin_x + sx(6), pin_y + sx(6)),
        fill=white,
        outline=ink,
        width=sx(2),
    )


def comic_scene_setting(scene: dict[str, Any], scene_index: int) -> str:
    """Choose a visibly different set that still matches the narrated action."""

    text = " ".join(
        str(scene.get(key, ""))
        for key in ("visualPrompt", "onScreenText", "narration")
    ).lower()
    rules = (
        ("serving", ("serve", "serves", "finished", "presents", "shares", "sunset", "journal", "complete")),
        ("wok", ("wok", "stir-f", "flame", "toss", "folds in", "cooking", "heat")),
        ("entrance", ("doorway", "opens her", "sunrise", "delivery", "receives")),
        ("market", ("market cart", "market stall", "cart", "pulls it free")),
        ("pantry", ("shelf", "shelves", "trail", "clue", "washes", "sorts", "crushes")),
        ("prep", ("lays out", "arranged", "ingredient", "missing", "basket", "selects", "compares")),
    )
    for setting, terms in rules:
        if any(term in text for term in terms):
            return setting
    return ("entrance", "prep", "pantry", "market", "wok", "serving")[
        scene_index % 6
    ]


def draw_comic_environment(
    draw: ImageDraw.ImageDraw,
    scene: dict[str, Any],
    *,
    scene_index: int,
    frame_index: int,
    box: tuple[int, int, int, int],
) -> str:
    """Draw a scene-matched animated set instead of recycling one kitchen."""

    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    ink = (31, 31, 40)
    movement = round(math.sin(frame_index * math.pi / 4) * max(4, width * 0.008))
    setting = comic_scene_setting(scene, scene_index)
    detail_variant = scene_index % 4

    if setting == "entrance":
        # Bangkok kitchen exterior at sunrise: sky, rooftops, awning, door, plants.
        horizon = top + round(height * 0.46)
        sky_top = (255, 181, 108)
        sky_bottom = (250, 226, 166)
        for y in range(top, horizon):
            ratio = (y - top) / max(1, horizon - top)
            color = tuple(
                round(a + (b - a) * ratio)
                for a, b in zip(sky_top, sky_bottom, strict=True)
            )
            draw.line((left, y, right, y), fill=color)
        sun_x = left + round(width * (0.22 + detail_variant * 0.04)) + movement
        sun_y = top + round(height * 0.22)
        sun_r = max(34, round(width * 0.075))
        draw.ellipse(
            (sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r),
            fill=(255, 236, 146),
            outline=(177, 91, 65),
            width=5,
        )
        for building in range(5):
            bx = left + building * round(width / 4.5) - 25
            roof_y = horizon - 28 - (building % 2) * 24
            draw.rectangle((bx, roof_y, bx + round(width * 0.28), bottom), fill=(112, 132, 137), outline=ink, width=4)
            draw.polygon(
                ((bx - 10, roof_y), (bx + round(width * 0.14), roof_y - 58), (bx + round(width * 0.29), roof_y)),
                fill=(173, 72, 55),
                outline=ink,
            )
        shop_left = left + round(width * 0.37)
        shop_right = right - round(width * 0.05)
        shop_top = top + round(height * 0.26)
        draw.rectangle((shop_left, shop_top, shop_right, bottom), fill=(62, 146, 147), outline=ink, width=7)
        awning_y = shop_top + round(height * 0.13)
        stripe_width = max(34, round((shop_right - shop_left) / 6))
        for stripe in range(6):
            sx = shop_left + stripe * stripe_width
            draw.polygon(
                ((sx, awning_y), (min(shop_right, sx + stripe_width), awning_y), (min(shop_right, sx + stripe_width + 10), awning_y + 58 + movement // 3), (sx - 4, awning_y + 58 - movement // 3)),
                fill=(244, 224, 179) if stripe % 2 == 0 else (218, 78, 70),
                outline=ink,
            )
        door_left = shop_left + round((shop_right - shop_left) * 0.48)
        draw.rectangle((door_left, awning_y + 58, shop_right - 24, bottom), fill=(43, 87, 94), outline=ink, width=6)
        draw.ellipse((shop_left + 28, bottom - 105, shop_left + 94, bottom - 39), fill=(49, 151, 87), outline=ink, width=5)
        draw.rectangle((shop_left + 43, bottom - 44, shop_left + 80, bottom), fill=(165, 91, 53), outline=ink, width=4)

    elif setting == "prep":
        # Bright prep counter with tiled wall, open window, cutting board and bowls.
        draw.rectangle(box, fill=(216, 239, 225))
        tile = max(62, width // 8)
        for x in range(left, right + 1, tile):
            draw.line((x, top, x, bottom), fill=(151, 194, 181), width=3)
        for y in range(top, bottom + 1, tile):
            draw.line((left, y, right, y), fill=(151, 194, 181), width=3)
        window = (left + 30, top + 34, left + round(width * 0.43), top + round(height * 0.42))
        draw.rectangle(window, fill=(117, 202, 226), outline=ink, width=8)
        window_mid = (window[0] + window[2]) // 2
        draw.line((window_mid, window[1], window_mid, window[3]), fill=ink, width=5)
        draw.line((window[0], (window[1] + window[3]) // 2, window[2], (window[1] + window[3]) // 2), fill=ink, width=5)
        counter_y = top + round(height * 0.61)
        draw.rectangle((left, counter_y, right, bottom), fill=(151, 88, 55), outline=ink, width=6)
        board_left = left + round(width * 0.14) + movement
        draw.rounded_rectangle((board_left, counter_y - 34, board_left + round(width * 0.31), counter_y + 48), radius=16, fill=(224, 171, 96), outline=ink, width=5)
        for bowl_index, color in enumerate(((227, 73, 64), (63, 159, 91), (246, 195, 73))):
            bowl_x = left + round(width * (0.12 + bowl_index * 0.14))
            draw.pieslice((bowl_x, counter_y - 105, bowl_x + 82, counter_y - 22), 0, 180, fill=color, outline=ink, width=5)
        for leaf_index in range(5):
            draw_comic_leaf(draw, board_left + 34 + leaf_index * 27, counter_y - 8 + (leaf_index % 2) * 14, 14, bright=True)

    elif setting == "pantry":
        # Narrow pantry/wash area with shelves and an animated basil clue trail.
        draw.rectangle(box, fill=(235, 210, 157))
        back_left = left + round(width * 0.25)
        back_right = right - round(width * 0.25)
        draw.polygon(((left, top), (back_left, top + 70), (back_left, bottom), (left, bottom)), fill=(190, 117, 73), outline=ink)
        draw.polygon(((right, top), (back_right, top + 70), (back_right, bottom), (right, bottom)), fill=(169, 101, 71), outline=ink)
        for shelf_index in range(3):
            shelf_y = top + 92 + shelf_index * round(height * 0.21)
            draw.line((left + 20, shelf_y, back_left + 18, shelf_y + 18), fill=ink, width=9)
            draw.line((right - 20, shelf_y, back_right - 18, shelf_y + 18), fill=ink, width=9)
            for side in (-1, 1):
                jar_x = back_left - 78 if side < 0 else back_right + 28
                jar_x += movement // 3 * (1 if shelf_index % 2 else -1)
                draw.rounded_rectangle((jar_x, shelf_y - 58, jar_x + 48, shelf_y - 5), radius=7, fill=((83, 159, 111), (232, 151, 73), (196, 75, 73))[shelf_index], outline=ink, width=4)
        sink_y = bottom - round(height * 0.22)
        draw.rectangle((back_left + 14, sink_y, back_right - 14, bottom), fill=(115, 163, 163), outline=ink, width=6)
        draw.arc((back_left + 58, sink_y - 76, back_left + 142, sink_y + 12), 180, 350, fill=(51, 65, 70), width=10)
        for drop in range(3):
            drop_x = back_left + 99 + ((frame_index + drop * 2) % 6 - 3) * 3
            drop_y = sink_y - 3 + ((frame_index + drop * 3) % 8) * 12
            draw.ellipse((drop_x - 5, drop_y - 9, drop_x + 5, drop_y + 9), fill=(74, 180, 216))
        for leaf_index in range(8):
            trail_x = left + round(width * (0.18 + leaf_index * 0.085)) + (movement if leaf_index % 2 else 0)
            trail_y = bottom - 50 - (leaf_index % 3) * 24
            draw_comic_leaf(draw, trail_x, trail_y, 13, bright=(leaf_index + frame_index) % 2 == 0)

    elif setting == "market":
        # Outdoor market lane with a moving awning, cart, produce and pennants.
        sky_end = top + round(height * 0.36)
        draw.rectangle((left, top, right, sky_end), fill=(132, 210, 220))
        draw.rectangle((left, sky_end, right, bottom), fill=(222, 177, 116))
        for stall in range(3):
            stall_left = left - 40 + stall * round(width * 0.36)
            stall_right = stall_left + round(width * 0.42)
            stall_top = top + 65 + (stall % 2) * 45
            draw.rectangle((stall_left, stall_top + 70, stall_right, bottom), fill=(100, 143, 124), outline=ink, width=5)
            draw.polygon(((stall_left - 16, stall_top + movement // 3), (stall_right + 16, stall_top - movement // 3), (stall_right - 8, stall_top + 86), (stall_left + 8, stall_top + 86)), fill=(219, 72, 69) if stall % 2 == 0 else (244, 193, 72), outline=ink)
        cart_x = left + round(width * 0.13) + movement
        cart_y = bottom - round(height * 0.29)
        draw.rounded_rectangle((cart_x, cart_y, cart_x + round(width * 0.40), bottom - 58), radius=18, fill=(194, 127, 65), outline=ink, width=7)
        for wheel_x in (cart_x + 58, cart_x + round(width * 0.34)):
            draw.ellipse((wheel_x - 32, bottom - 87, wheel_x + 32, bottom - 23), fill=(55, 56, 61), outline=ink, width=6)
            spoke = frame_index * math.pi / 4
            draw.line((wheel_x, bottom - 55, wheel_x + math.cos(spoke) * 26, bottom - 55 + math.sin(spoke) * 26), fill=(224, 221, 202), width=4)
        for basket_index in range(3):
            basket_x = cart_x + 36 + basket_index * 78
            draw.ellipse((basket_x, cart_y - 47, basket_x + 76, cart_y + 22), fill=(221, 155, 71), outline=ink, width=5)
            draw_comic_leaf(draw, basket_x + 38, cart_y - 44 - (basket_index % 2) * 10, 18, bright=True)
        flag_y = top + 32
        for flag in range(8):
            flag_x = left + flag * round(width / 7)
            draw.polygon(((flag_x, flag_y), (flag_x + 34, flag_y + 8 + movement // 3), (flag_x + 17, flag_y + 55)), fill=((243, 76, 74), (249, 197, 73), (54, 161, 153))[flag % 3], outline=ink)

    elif setting == "wok":
        # Close cooking station with a hood, hot wok, flames and moving steam.
        draw.rectangle(box, fill=(82, 99, 111))
        tile = max(56, width // 9)
        for x in range(left, right + 1, tile):
            draw.line((x, top, x, bottom), fill=(118, 137, 146), width=3)
        for y in range(top, bottom + 1, tile):
            draw.line((left, y, right, y), fill=(118, 137, 146), width=3)
        hood_center = left + round(width * 0.34)
        hood_top = top + 30
        draw.polygon(((hood_center - 150, hood_top), (hood_center + 150, hood_top), (hood_center + 105, hood_top + 145), (hood_center - 105, hood_top + 145)), fill=(160, 172, 174), outline=ink)
        stove_y = bottom - round(height * 0.23)
        draw.rectangle((left, stove_y, right, bottom), fill=(47, 55, 62), outline=ink, width=7)
        wok_x = left + round(width * (0.30 + 0.035 * detail_variant))
        wok_y = stove_y - 42
        draw.ellipse((wok_x - 135, wok_y - 44, wok_x + 135, wok_y + 94), fill=(39, 44, 51), outline=(13, 15, 20), width=11)
        draw.line((wok_x + 100, wok_y + 30, wok_x + 240, wok_y - 15 + movement), fill=(25, 27, 31), width=24)
        for flame in range(6):
            fx = wok_x - 88 + flame * 35
            flame_h = 42 + ((frame_index + flame + detail_variant) % 4) * 12
            draw.polygon(((fx - 14, stove_y + 14), (fx, stove_y + 14 - flame_h), (fx + 14, stove_y + 14)), fill=(252, 103, 49) if flame % 2 else (255, 196, 55), outline=(94, 45, 38))
        for steam in range(4):
            sx = wok_x - 66 + steam * 45 + movement
            sy = wok_y - 80 - steam * 13
            draw.arc((sx - 25, sy - 65, sx + 25, sy + 32), 80, 280, fill=(250, 250, 235), width=9)
        for leaf_index in range(5):
            angle = (frame_index + leaf_index) * 0.7
            leaf_x = wok_x + round(math.cos(angle) * (50 + leaf_index * 8))
            leaf_y = wok_y - 55 - round(abs(math.sin(angle)) * (70 + leaf_index * 6))
            draw_comic_leaf(draw, leaf_x, leaf_y, 13, bright=True)

    else:
        # Serving nook at sunset with a window, table, dish and twinkling lights.
        draw.rectangle(box, fill=(72, 88, 106))
        window = (left + 28, top + 32, right - 28, top + round(height * 0.48))
        draw.rectangle(window, fill=(244, 151, 102), outline=ink, width=8)
        horizon = window[1] + round((window[3] - window[1]) * 0.60)
        draw.rectangle((window[0] + 7, horizon, window[2] - 7, window[3] - 7), fill=(112, 85, 132))
        sunset_x = window[0] + round((window[2] - window[0]) * 0.25) + movement
        draw.ellipse((sunset_x - 42, horizon - 65, sunset_x + 42, horizon + 19), fill=(255, 221, 105), outline=(151, 76, 69), width=5)
        for building in range(7):
            bx = window[0] + 8 + building * round((window[2] - window[0] - 16) / 7)
            by = horizon - 8 - (building % 3) * 26
            draw.rectangle((bx, by, bx + 62, window[3] - 7), fill=(74, 67, 93))
        table_y = bottom - round(height * 0.26)
        draw.rectangle((left, table_y, right, bottom), fill=(125, 76, 56), outline=ink, width=7)
        plate_x = left + round(width * 0.30) + movement // 2
        draw.ellipse((plate_x - 128, table_y - 50, plate_x + 128, table_y + 52), fill=(251, 245, 222), outline=ink, width=7)
        for leaf_index in range(7):
            draw_comic_leaf(draw, plate_x - 72 + leaf_index * 24, table_y - 3 + (leaf_index % 3) * 12, 13, bright=True)
        draw.line((left + 24, top + 22, right - 24, top + 52), fill=(34, 35, 43), width=5)
        for bulb in range(9):
            bulb_x = left + 38 + bulb * round((width - 76) / 8)
            bulb_y = top + 25 + round((bulb_x - left) / max(1, width) * 28)
            glow = (255, 235, 140) if (bulb + frame_index) % 3 else (255, 188, 85)
            draw.ellipse((bulb_x - 10, bulb_y - 7, bulb_x + 10, bulb_y + 13), fill=glow, outline=ink, width=3)

    return setting


def build_motion_comic_frame(
    scene: dict[str, Any],
    *,
    scene_index: int,
    total_scenes: int,
    frame_index: int,
    dimensions: tuple[int, int],
    output: Path,
) -> None:
    width, height = dimensions
    beat = min(5, scene_index * 6 // max(1, total_scenes))
    palettes = (
        ((255, 190, 92), (241, 92, 93), (37, 37, 68)),
        ((82, 206, 195), (31, 114, 136), (16, 35, 58)),
        ((180, 132, 255), (76, 66, 158), (28, 28, 61)),
    )
    top_color, middle_color, ink = palettes[scene_index % len(palettes)]
    base = Image.new("RGB", dimensions, middle_color)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(
            round(a + (b - a) * ratio)
            for a, b in zip(top_color, middle_color, strict=True)
        )
        draw.line((0, y, width, y), fill=color)

    # Comic halftone texture and two offset panels create depth during camera moves.
    dot_step = max(24, width // 24)
    for y in range(0, height, dot_step):
        for x in range((y // dot_step % 2) * (dot_step // 2), width, dot_step):
            radius = 2 + ((x + y + frame_index) // dot_step) % 3
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=ink)
    panel_margin = max(22, width // 28)
    draw.rounded_rectangle(
        (
            panel_margin,
            round(height * 0.20),
            width - panel_margin,
            height - panel_margin,
        ),
        radius=max(24, width // 22),
        fill=(250, 238, 213),
        outline=(20, 22, 32),
        width=max(8, width // 80),
    )
    action_top = round(height * 0.31)
    draw.rectangle(
        (
            panel_margin + 12,
            action_top,
            width - panel_margin - 12,
            height - panel_margin - 12,
        ),
        fill=(245, 224, 183),
    )

    setting = draw_comic_environment(
        draw,
        scene,
        scene_index=scene_index,
        frame_index=frame_index,
        box=(
            panel_margin + 12,
            action_top,
            width - panel_margin - 12,
            height - panel_margin - 12,
        ),
    )

    # Action lines belong only to energetic market and wok shots. Quieter scenes
    # use small sparkles so the six sets do not share the same visual silhouette.
    if setting in {"market", "wok"}:
        line_center = (round(width * 0.48), round(height * 0.56))
        for ray in range(10):
            angle = (ray / 10) * math.tau + frame_index * 0.015
            start_r, end_r = 175, 235 + (ray % 3) * 18
            draw.line(
                (
                    line_center[0] + math.cos(angle) * start_r,
                    line_center[1] + math.sin(angle) * start_r,
                    line_center[0] + math.cos(angle) * end_r,
                    line_center[1] + math.sin(angle) * end_r,
                ),
                fill=(57, 50, 62),
                width=5,
            )
    else:
        for sparkle in range(6):
            sx = panel_margin + 54 + (sparkle * 97 + scene_index * 31) % max(100, width - panel_margin * 2 - 108)
            sy = action_top + 54 + (sparkle * 113 + frame_index * 7) % max(120, height - action_top - panel_margin - 150)
            radius = 7 + (sparkle + frame_index) % 5
            draw.line((sx - radius, sy, sx + radius, sy), fill=(255, 245, 196), width=4)
            draw.line((sx, sy - radius, sx, sy + radius), fill=(255, 245, 196), width=4)

    draw_mali_character(
        base,
        center_x=round(width * (0.70 if scene_index % 2 == 0 else 0.73)),
        foot_y=height - panel_margin - 20,
        scale=0.84 if height > width else 0.64,
        frame_index=frame_index,
        pose=beat,
    )

    # Speech-card copy is short and always tied to this exact scene.
    bubble = Image.new("RGBA", dimensions, (0, 0, 0, 0))
    bubble_draw = ImageDraw.Draw(bubble)
    bubble_left = panel_margin + 10
    bubble_top = panel_margin + 54
    bubble_right = width - panel_margin - 10
    bubble_bottom = round(height * 0.195)
    bubble_draw.rounded_rectangle(
        (bubble_left, bubble_top, bubble_right, bubble_bottom),
        radius=max(24, width // 24),
        fill=(255, 253, 244, 248),
        outline=(22, 24, 33, 255),
        width=max(7, width // 92),
    )
    tail_x = round(width * 0.69)
    bubble_draw.polygon(
        (
            (tail_x - 22, bubble_bottom - 4),
            (tail_x + 36, bubble_bottom - 4),
            (tail_x + 18, bubble_bottom + 44),
        ),
        fill=(255, 253, 244, 248),
        outline=(22, 24, 33, 255),
    )
    base = Image.alpha_composite(base.convert("RGBA"), bubble).convert("RGB")
    draw = ImageDraw.Draw(base)
    label_font = font(max(18, round(width * 0.029)), bold=True)
    title_font = font(max(34, round(width * 0.057)), bold=True)
    label = "MALI • ORIGINAL MOTION COMIC"
    draw.text(
        (bubble_left + 24, bubble_top - 40),
        label,
        font=label_font,
        fill=(255, 251, 233),
        stroke_width=3,
        stroke_fill=(20, 23, 33),
    )
    lines = wrapped_lines(
        draw,
        str(scene["onScreenText"]),
        title_font,
        bubble_right - bubble_left - 54,
    )[:2]
    line_height = round(title_font.size * 1.08)
    text_y = bubble_top + max(16, (bubble_bottom - bubble_top - len(lines) * line_height) // 2)
    for line_index, line in enumerate(lines):
        draw.text(
            (bubble_left + 27, text_y + line_index * line_height),
            line,
            font=title_font,
            fill=(29, 31, 42),
        )
    counter = f"{scene_index + 1:02d}/{total_scenes:02d}"
    counter_width = draw.textbbox((0, 0), counter, font=label_font)[2]
    draw.text(
        (width - panel_margin - counter_width, panel_margin),
        counter,
        font=label_font,
        fill=(255, 251, 233),
        stroke_width=3,
        stroke_fill=(20, 23, 33),
    )
    base.save(output, format="PNG", optimize=True)


def render_motion_comic(
    pack: dict[str, Any], video_format: str, work: Path
) -> Path:
    dimensions = (720, 1280) if video_format == "short" else (1280, 720)
    width, height = dimensions
    scene_files: list[Path] = []
    frame_count = 8
    for index, scene in enumerate(pack["scenes"]):
        pattern = work / f"comic-{index:02d}-%02d.png"
        for frame_index in range(frame_count):
            build_motion_comic_frame(
                scene,
                scene_index=index,
                total_scenes=len(pack["scenes"]),
                frame_index=frame_index,
                dimensions=dimensions,
                output=work / f"comic-{index:02d}-{frame_index:02d}.png",
            )

        audio = work / f"voice-{index:02d}.wav"
        synthesize_scene(str(scene["narration"]), audio)
        target = int(scene["durationSeconds"])
        audio_length = wav_seconds(audio)
        tempo = max(1.0, audio_length / max(1.0, target - 0.25))
        scene["_speechDuration"] = min(target - 0.08, audio_length / tempo)
        fade_out = max(0.0, target - 0.28)
        audio_filter = (
            f"{atempo_chain(tempo)},"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            f"apad=pad_dur={target},atrim=duration={target},"
            f"afade=t=in:st=0:d=0.16,afade=t=out:st={fade_out:.2f}:d=0.28"
        )
        enlarged_width = round(width * 1.10 / 2) * 2
        enlarged_height = round(height * 1.10 / 2) * 2
        camera_filter = (
            f"[0:v]scale={enlarged_width}:{enlarged_height}:flags=lanczos,"
            f"crop={width}:{height}:"
            "x='(in_w-out_w)*(0.50+0.30*sin(t*0.52))':"
            "y='(in_h-out_h)*(0.50+0.24*cos(t*0.47))',"
            "fps=30,"
            "fade=t=in:st=0:d=0.18:color=black,"
            f"fade=t=out:st={fade_out:.2f}:d=0.28:color=black,"
            "format=yuv420p[video]"
        )
        scene_file = work / f"scene-{index:02d}.mp4"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-stream_loop",
                "-1",
                "-framerate",
                "8",
                "-i",
                str(pattern),
                "-i",
                str(audio),
                "-filter_complex",
                camera_filter,
                "-map",
                "[video]",
                "-map",
                "1:a:0",
                "-af",
                audio_filter,
                "-t",
                str(target),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
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
            timeout=420,
        )
        verify_scene_motion(scene_file, work, index, comic=True)
        scene_files.append(scene_file)

    concat = work / "scenes.txt"
    concat.write_text(
        "\n".join(f"file '{path.name}'" for path in scene_files) + "\n",
        encoding="utf-8",
    )
    assembled = work / "assembled.mp4"
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
            str(assembled),
        ],
        timeout=300,
    )
    captions = work / "captions.ass"
    write_captions(pack, captions, dimensions, video_format)
    caption_path = captions.as_posix().replace("\\", "/").replace(":", r"\:")
    output = work / "factforge.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(assembled),
            "-vf",
            f"ass=filename='{caption_path}'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        timeout=420,
    )
    size = output.stat().st_size
    if size < 20_000 or size > 95 * 1024 * 1024:
        raise RuntimeError("The finished motion comic fell outside the upload size limit.")
    print(
        f"Original motion-comic gate passed for all {len(scene_files)} animated scenes."
    )
    return output


def render_video(pack: dict[str, Any], video_format: str, work: Path) -> Path:
    profile = video_profile_for_topic(str(pack.get("topic", "")))
    if profile and profile.get("kind") == "comic":
        return render_motion_comic(pack, video_format, work)
    dimensions = (720, 1280) if video_format == "short" else (1280, 720)
    width, height = dimensions
    if not HOST_SHEET.exists():
        raise RuntimeError("The consistent FactForge host asset was missing.")
    if video_format != "short":
        raise RuntimeError(
            "Live-footage gate stopped this long-form upload: only the inspected "
            "Shorts timelines are enabled while Autopilot is paused for quality review."
        )
    video_cache: dict[str, Path] = {}
    scene_files: list[Path] = []
    for index, scene in enumerate(pack["scenes"]):
        source_video = acquire_scene_video(scene, work, video_cache)
        overlay = build_live_overlay(
            scene,
            index,
            len(pack["scenes"]),
            dimensions,
            work,
        )
        audio = work / f"voice-{index:02d}.wav"
        synthesize_scene(str(scene["narration"]), audio)
        target = int(scene["durationSeconds"])
        audio_length = wav_seconds(audio)
        tempo = max(1.0, audio_length / max(1.0, target - 0.25))
        scene["_speechDuration"] = min(target - 0.08, audio_length / tempo)
        fade_out = max(0.0, target - 0.28)
        audio_filter = (
            f"{atempo_chain(tempo)},"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            f"apad=pad_dur={target},atrim=duration={target},"
            f"afade=t=in:st=0:d=0.16,afade=t=out:st={fade_out:.2f}:d=0.28"
        )
        scene_file = work / f"scene-{index:02d}.mp4"
        clip_start = max(0.0, float(scene.get("_clipStartSeconds", 0.0)))
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps=30[background];"
            "[1:v]format=rgba[overlay];"
            "[background][overlay]overlay=0:0:format=auto,"
            "fade=t=in:st=0:d=0.22:color=black,"
            f"fade=t=out:st={max(0.0, target - 0.28):.2f}:d=0.28:color=black,"
            "format=yuv420p[video]"
        )
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-stream_loop",
                "-1",
                "-ss",
                f"{clip_start:.3f}",
                "-i",
                str(source_video),
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                str(overlay),
                "-i",
                str(audio),
                "-filter_complex",
                filter_complex,
                "-map",
                "[video]",
                "-map",
                "2:a:0",
                "-af",
                audio_filter,
                "-t",
                str(target),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
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
            timeout=420,
        )
        verify_scene_motion(scene_file, work, index)
        scene_files.append(scene_file)

    if len(scene_files) != len(pack["scenes"]):
        raise RuntimeError(
            "Live-footage gate stopped the upload: every scene must use moving video."
        )
    print(f"Live-footage gate passed for all {len(scene_files)} scenes.")

    concat = work / "scenes.txt"
    concat.write_text(
        "\n".join(f"file '{path.name}'" for path in scene_files) + "\n",
        encoding="utf-8",
    )
    assembled = work / "assembled.mp4"
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
            str(assembled),
        ],
        timeout=300,
    )
    presenter_audio = work / "presenter-audio.wav"
    intro, outro_start, outro = build_presenter_audio(
        assembled, pack, presenter_audio
    )
    presenter = animate_presenter(presenter_audio, work)
    captions = work / "captions.ass"
    write_captions(pack, captions, dimensions, video_format)
    caption_path = captions.as_posix().replace("\\", "/").replace(":", r"\:")
    subtitle_filter = f"ass=filename='{caption_path}'"
    host_height = 620 if video_format == "short" else 500
    host_margin = 10 if video_format == "short" else 28
    host_end = intro + outro
    filter_complex = (
        "[1:v]setpts=PTS-STARTPTS,fps=30,"
        "chromakey=0x00FF00:0.28:0.10,format=rgba,"
        f"scale=-2:{host_height},split=2[host-intro-raw][host-outro-raw];"
        f"[host-intro-raw]trim=start=0:end={intro:.3f},"
        "setpts=PTS-STARTPTS[host-intro];"
        f"[host-outro-raw]trim=start={intro:.3f}:end={host_end:.3f},"
        f"setpts=PTS-STARTPTS+{outro_start:.3f}/TB[host-outro];"
        "[0:v][host-intro]overlay="
        f"x='main_w-overlay_w-{host_margin}+4*sin(1.35*t)':"
        "y='main_h-overlay_h+8+5*sin(1.9*t)':"
        "eof_action=pass:shortest=0[with-intro];"
        "[with-intro][host-outro]overlay="
        f"x='main_w-overlay_w-{host_margin}+4*sin(1.35*t)':"
        "y='main_h-overlay_h+8+5*sin(1.9*t)':"
        "eof_action=pass:shortest=0[hosted];"
        f"[hosted]{subtitle_filter}[video]"
    )
    output = work / "factforge.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(assembled),
            "-i",
            str(presenter),
            "-filter_complex",
            filter_complex,
            "-map",
            "[video]",
            "-map",
            "0:a:0",
            "-t",
            f"{sum(float(scene['durationSeconds']) for scene in pack['scenes']):.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-c:a",
            "copy",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        timeout=420,
    )
    size = output.stat().st_size
    if size < 20_000 or size > 95 * 1024 * 1024:
        raise RuntimeError("The finished MP4 fell outside the upload size limit.")
    return output


def remove_internal_scene_fields(pack: dict[str, Any]) -> None:
    for scene in pack.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        for key in (
            "_clipStartSeconds",
            "_imageCandidates",
            "_mediaMatch",
            "_renderStyle",
            "_sourceUsed",
            "_speechDuration",
            "_videoCandidates",
        ):
            scene.pop(key, None)


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


def store_metadata(job_id: str, pack: dict[str, Any]) -> None:
    """Persist a replay-safe public content pack before the expensive render."""
    public_pack = json.loads(json.dumps(pack))
    remove_internal_scene_fields(public_pack)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            factforge_request(
                "POST",
                f"/api/free-runner/jobs/{job_id}/metadata",
                payload={"pack": public_pack},
                timeout=300,
            )
            return
        except FactForgeError as error:
            if error.status < 500:
                raise
            last_error = error
        except requests.RequestException as error:
            last_error = error
        if attempt < 2:
            print(
                f"Metadata save attempt {attempt + 1} timed out; retrying safely."
            )
            time.sleep(2 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("FactForge did not accept the content metadata.")


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
        elif action == "render" and isinstance(job.get("pack"), dict):
            pack = job["pack"]
        else:
            raise RuntimeError("FactForge returned an unsupported runner action.")
        attach_rights_safe_videos(pack)

        if action == "create":
            store_metadata(job_id, pack)

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
