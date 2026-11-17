import os, requests
from dotenv import load_dotenv
load_dotenv()

CID = os.getenv("TWITCH_CLIENT_ID")
SECRET = os.getenv("TWITCH_CLIENT_SECRET")

def twitch_token():
    r = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CID, "client_secret": SECRET,
        "grant_type": "client_credentials"})
    return r.json()["access_token"]

def latest_vod(login, token):
    h = {"Client-Id": CID, "Authorization": f"Bearer {token}"}
    users = requests.get("https://api.twitch.tv/helix/users",
                         params={"login": login}, headers=h).json()["data"]
    if not users:
        return None
    v = requests.get("https://api.twitch.tv/helix/videos",
                     params={"user_id": users[0]["id"], "type": "archive", "first": 1},
                     headers=h).json()["data"]
    return v[0] if v else None
