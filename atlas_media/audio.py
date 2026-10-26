import os
from urllib.parse import quote
from typing import Any, Dict, List

import httpx

UNSPLASH_ACCESS_KEY = os.getenv("ATLAS_MEDIA_UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("ATLAS_MEDIA_PEXELS_API_KEY")
OUTPUT_DIR = os.getenv("ATLAS_MEDIA_OUTPUT_DIR", "./output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_unsplash_images(query: str, count: int = 3) -> List[Dict[str, Any]]:
    if not UNSPLASH_ACCESS_KEY:
        return []
    url = "https://api.unsplash.com/search/photos"
    params = {"query": query, "per_page": count, "page": 1}
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    resp = httpx.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for item in data.get("results", []):
        items.append({
            "source": "unsplash",
            "image_url": item.get("urls", {}).get("regular"),
            "thumb_url": item.get("urls", {}).get("small"),
            "title": item.get("alt_description") or query,
            "author": item.get("user", {}).get("name"),
        })
    return items


def fetch_pexels_video(query: str, count: int = 2) -> List[Dict[str, Any]]:
    if not PEXELS_API_KEY:
        return []
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": count, "page": 1}
    resp = httpx.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for item in data.get("videos", []):
        best = max(item.get("video_files", []), key=lambda x: x.get("height", 0) * x.get("width", 0), default=None)
        if best:
            items.append({
                "source": "pexels",
                "video_url": best.get("link"),
                "thumbnail": item.get("image"),
                "title": item.get("user", {}).get("name") or query,
            })
    return items


def fetch_wikimedia_images(query: str, count: int = 3) -> List[Dict[str, Any]]:
    safe_query = quote(query)
    url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&generator=search&gsrsearch={safe_query}&gsrnamespace=6&prop=imageinfo"
        "&iiprop=url|extmetadata&iiurlwidth=1200&format=json&gsrlimit=5"
    )
    resp = httpx.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = page.get("imageinfo", [])
        if not info:
            continue
        image = info[0]
        items.append({
            "source": "wikimedia",
            "image_url": image.get("thumburl") or image.get("url"),
            "title": page.get("title") or query,
        })
        if len(items) >= count:
            break
    return items


def download_file(url: str, file_path: str) -> str:
    if not url:
        raise ValueError("download_file called with empty URL")
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    with open(file_path, "wb") as fh:
        fh.write(resp.content)
    return file_path


def collect_media_assets(prompt: str, image_limit: int = 3, video_limit: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    images: List[Dict[str, Any]] = []
    videos: List[Dict[str, Any]] = []

    for fetcher in (fetch_unsplash_images, fetch_wikimedia_images):
        try:
            images.extend(fetcher(prompt, count=image_limit))
        except Exception:
            pass

    try:
        videos.extend(fetch_pexels_video(prompt, count=video_limit))
    except Exception:
        pass

    dedup_images = []
    seen = set()
    for item in images:
        key = item.get("image_url") or item.get("thumb_url")
        if not key or key in seen:
            continue
        seen.add(key)
        dedup_images.append(item)

    dedup_videos = []
    seen_v = set()
    for item in videos:
        key = item.get("video_url")
        if not key or key in seen_v:
            continue
        seen_v.add(key)
        dedup_videos.append(item)

    return {"images": dedup_images, "videos": dedup_videos}
