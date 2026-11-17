import os, subprocess, json, re, collections
from faster_whisper import WhisperModel

CLIPS = int(os.getenv("CLIPS_PER_VOD", 5))
MIN_LEN = int(os.getenv("MIN_CLIP_SECONDS", 30))
MAX_LEN = int(os.getenv("MAX_CLIP_SECONDS", 60))
LEN = MIN_LEN
whisper = WhisperModel("small", compute_type="int8")

def download_vod(url, out):
    subprocess.run(["yt-dlp", "-f", "best[height<=720]", "-o", out, url], check=True)
    return out

def download_chat(vod_id):
    out = f"chat_{vod_id}.json"
    subprocess.run(["TwitchDownloaderCLI", "chatdownload",
                    "--id", vod_id, "-o", out], check=True)
    return out

def chat_spikes(chat_json):
    data = json.load(open(chat_json))
    buckets = collections.Counter()
    for c in data["comments"]:
        buckets[int(c["content_offset_seconds"] // 10)] += 1
    return buckets

def loudness(vod):
    r = subprocess.run([
        "ffmpeg", "-i", vod, "-vn", "-af",
        "aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,"
        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
        "-f", "null", "-"], capture_output=True, text=True)
    vals = re.findall(r"RMS_level=(-?[\d.]+)", r.stdout)
    scores = collections.Counter()
    for i, v in enumerate(vals):
        try:
            scores[i // 10] += max(0.0, 100 + float(v))
        except ValueError:
            pass
    return scores

def pick_moments(chat, loud):
    total = collections.Counter()
    for k, v in chat.items():
        total[k] += v * 2
    for k, v in loud.items():
        total[k] += v / 10
    chosen = []
    for bucket, _ in total.most_common():
        start = max(0, bucket * 10 - MIN_LEN // 2)
        if all(abs(start - s) > MIN_LEN for s in chosen):
            chosen.append(start)
        if len(chosen) == CLIPS:
            break
    return chosen

def clip_length(chat, loud, start):
    first = start // 10
    avg = (sum(chat.values()) / max(1, len(chat))) * 1.5
    length = MIN_LEN
    while length < MAX_LEN:
        bucket = first + length // 10
        if chat.get(bucket, 0) + loud.get(bucket, 0) / 10 < avg:
            break
        length += 10
    return min(max(length, MIN_LEN), MAX_LEN)

def ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02}:{m:02}:{s:06.3f}".replace(".", ",")

def make_clip(vod, start, out, length=None):
    length = length or MIN_LEN
    raw = out.replace(".mp4", "_raw.mp4")
    subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-t", str(length),
                    "-i", vod, "-c", "copy", raw], check=True)
    segs, _ = whisper.transcribe(raw)
    srt = out.replace(".mp4", ".srt")
    with open(srt, "w") as f:
        for i, s in enumerate(segs, 1):
            f.write(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text.strip()}\n\n")
    vf = ("crop=ih*9/16:ih,scale=720:1280,"
          f"subtitles={srt}:force_style='FontSize=18,Bold=1,Alignment=2'")
    subprocess.run(["ffmpeg", "-y", "-i", raw, "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-c:a", "aac", out], check=True)
    return out
