import os, time, socket, subprocess, collections, threading, requests
import watcher, highlights

MULT = float(os.getenv("SPIKE_MULTIPLIER", 3))
MIN_MSGS = int(os.getenv("MIN_SPIKE_MESSAGES", 10))
COOLDOWN = int(os.getenv("COOLDOWN_SECONDS", 90))
WARMUP = 120

def is_live(login, token):
    h = {"Client-Id": watcher.CID, "Authorization": f"Bearer {token}"}
    r = requests.get("https://api.twitch.tv/helix/streams",
                     params={"user_login": login}, headers=h).json()
    return bool(r.get("data"))

def start_recorder(login, folder):
    os.makedirs(folder, exist_ok=True)
    cmd = (f"streamlink twitch.tv/{login} best -O | "
           f"ffmpeg -loglevel error -i pipe:0 -c copy -f segment "
           f"-segment_time 10 -segment_wrap 18 -reset_timestamps 1 "
           f"{folder}/seg_%02d.ts")
    return subprocess.Popen(cmd, shell=True)

class ChatCounter:
    def __init__(self, login):
        self.hits = collections.deque()
        self.s = socket.socket()
        self.s.connect(("irc.chat.twitch.tv", 6667))
        self.s.send(b"PASS SCHMOOPIIE\r\nNICK justinfan12345\r\n")
        self.s.send(f"JOIN #{login}\r\n".encode())
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            while True:
                data = self.s.recv(4096).decode(errors="ignore")
                if not data:
                    break
                if data.startswith("PING"):
                    self.s.send(b"PONG :tmi.twitch.tv\r\n")
                now = time.time()
                for line in data.split("\r\n"):
                    if "PRIVMSG" in line:
                        self.hits.append(now)
        except OSError:
            pass

    def rate(self, window=10):
        now = time.time()
        while self.hits and self.hits[0] < now - 120:
            self.hits.popleft()
        return sum(1 for t in self.hits if t > now - window)

    def baseline(self):
        return max(1.0, len(self.hits) / 12)

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

def cut_latest(folder, out):
    segs = sorted((os.path.join(folder, f) for f in os.listdir(folder)
                   if f.endswith(".ts")), key=os.path.getmtime)[-6:]
    lst = os.path.join(folder, "list.txt")
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{os.path.abspath(s)}'\n")
    raw = out.replace(".mp4", "_live.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", raw], check=True)
    return highlights.make_clip(raw, 0, out, len(segs) * 10)

def watch(login, notify):
    token = watcher.twitch_token()
    while True:
        try:
            if not is_live(login, token):
                time.sleep(60)
                continue
            folder = f"live_{login}"
            rec = start_recorder(login, folder)
            chat = ChatCounter(login)
            began = time.time()
            last = 0
            while is_live(login, token):
                time.sleep(10)
                if time.time() - began < WARMUP:
                    continue
                r = chat.rate()
                if (r >= MIN_MSGS and r > MULT * chat.baseline()
                        and time.time() - last > COOLDOWN):
                    last = time.time()
                    time.sleep(8)
                    out = f"live_{login}_{int(time.time())}.mp4"
                    try:
                        notify(cut_latest(folder, out), login)
                    except Exception as e:
                        print("live clip failed:", e)
            rec.terminate()
            chat.close()
        except Exception as e:
            print("watch error:", e)
            time.sleep(60)
            token = watcher.twitch_token()
