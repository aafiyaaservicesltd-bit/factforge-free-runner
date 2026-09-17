#!/usr/bin/env python3

import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

FACTFORGE_URL = os.environ["FACTFORGE_URL"].rstrip("/")
IMPORT_PATH = os.environ.get(
    "FACTFORGE_IMPORT_PATH",
    "/api/free-runner/import-external",
)
VIDEO_URL = os.environ["HIGGSFIELD_VIDEO_URL"]
TITLE = os.environ.get("VIDEO_TITLE", "Mali Dubai Solo Travel")
TOKEN = os.environ["ACTIONS_ID_TOKEN"]
MAX_BYTES = 95 * 1024 * 1024


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode())


def main():
    with tempfile.TemporaryDirectory() as folder:
        video = Path(folder) / "video.mp4"

        download = urllib.request.Request(
            VIDEO_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FactForgeBridge/1.0)",
                "Accept": "video/mp4,application/octet-stream,*/*",
            },
        )

        print("Downloading Higgsfield MP4...", flush=True)
        with urllib.request.urlopen(download, timeout=900) as response:
            video.write_bytes(response.read())

        size = video.stat().st_size
        if size < 20_000 or size > MAX_BYTES:
            raise RuntimeError("MP4 size is outside the allowed limit.")

        digest = hashlib.sha256(video.read_bytes()).hexdigest()

        imported = post_json(
            FACTFORGE_URL + IMPORT_PATH,
            {
                "title": TITLE[:100],
                "visibility": "private",
                "source": "higgsfield",
                "source_url": VIDEO_URL,
                "sha256": digest,
                "size": size,
            },
        )

        job_id = str(imported.get("job_id", ""))
        if not job_id:
            raise RuntimeError("FactForge returned no job_id.")

        upload = urllib.request.Request(
            FACTFORGE_URL + f"/api/free-runner/jobs/{job_id}/video",
            data=video.read_bytes(),
            method="PUT",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "X-Content-Sha256": digest,
            },
        )

        with urllib.request.urlopen(upload, timeout=900):
            pass

        print(f"Private upload staged: {job_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Bridge failed: {error}", file=sys.stderr)
        raise SystemExit(1)
