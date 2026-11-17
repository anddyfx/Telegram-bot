import os, requests

TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN")
AUTO = os.getenv("AUTO_POST", "false").lower() == "true"
BASE = "https://open.tiktokapis.com/v2/post/publish"
H = {"Authorization": f"Bearer {TOKEN}",
     "Content-Type": "application/json; charset=UTF-8"}

def upload(path, caption):
    size = os.path.getsize(path)
    endpoint = "/video/init/" if AUTO else "/inbox/video/init/"
    body = {"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": size, "total_chunk_count": 1}}
    if AUTO:
        body["post_info"] = {"title": caption, "privacy_level": "PUBLIC_TO_EVERYONE"}
    r = requests.post(BASE + endpoint, headers=H, json=body).json()
    if "data" not in r or "upload_url" not in r["data"]:
        raise RuntimeError(f"TikTok init failed: {r}")
    with open(path, "rb") as f:
        requests.put(r["data"]["upload_url"], data=f, headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{size-1}/{size}"})
    return r["data"]["publish_id"]
