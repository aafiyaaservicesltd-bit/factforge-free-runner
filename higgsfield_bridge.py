#!/usr/bin/env python3
"""Stage a public Higgsfield MP4 as a private FactForge upload.

The FactForge site must expose FACTFORGE_IMPORT_PATH (default:
/api/free-runner/import-external) and accept the GitHub OIDC bearer token.
The endpoint returns {"job_id": "..."}; the existing runner upload contract
is then used to transfer the MP4. No publish call is made, so the YouTube item
remains private for review.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path


FACTFORGE_URL = os.environ["FACTFORGE_URL"].rstrip("/")
IMPORT_PATH = os.environ.get("FACTFORGE_IMPORT_PATH", "/api/free-runner/import-external")
VIDEO_URL = os.environ["HIGGSFIELD_VIDEO_URL"]
TITLE = os.environ.get("VIDEO_TITLE", "Mali Dubai Solo Travel")
DESCRIPTION = os.environ.get("VIDEO_DESCRIPTION", "")
OIDC_TOKEN = os.environ["ACTIONS_ID_TOKEN"]
MAX_BYTES = 95 * 1024 * 1024


def request_json(method: str, url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {OIDC_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode())
    if not isinstance(data, dict):
        raise RuntimeError("FactForge returned an invalid response.")
    return data


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="factforge-higgsfield-") as tmp:
        path = Path(tmp) / "video.mp4"
        print("Downloading Higgsfield MP4…", flush=True)
        urllib.request.urlretrieve(VIDEO_URL, path)
        size = path.stat().st_size
        if size < 20_000 or size > MAX_BYTES:
            raise RuntimeError(f"MP4 size {size} is outside the 20 KB–95 MB limit.")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()

        imported = request_json(
            "POST",
            FACTFORGE_URL + IMPORT_PATH,
            {
                "title": TITLE[:100],
                "description": DESCRIPTION[:5000],
                "visibility": "private",
                "source": "higgsfield",
                "source_url": VIDEO_URL,
                "sha256": digest,
                "size": size,
            },
        )
        job_id = str(imported.get("job_id", ""))
        if not job_id:
            raise RuntimeError("FactForge import endpoint returned no job_id.")

        upload_url = FACTFORGE_URL + f"/api/free-runner/jobs/{job_id}/video"
        req = urllib.request.Request(
            upload_url,
            data=path.read_bytes(),
            method="PUT",
            headers={
                "Authorization": f"Bearer {OIDC_TOKEN}",
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "X-Content-Sha256": digest,
            },
        )
        with urllib.request.urlopen(req, timeout=900) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(f"FactForge rejected the MP4 with HTTP {response.status}.")
        print(f"Staged privately: {job_id}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Bridge failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
