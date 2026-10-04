"""
One-time: get a YouTube refresh token on YOUR laptop (opens a browser).

1. Download the OAuth client JSON from Google Cloud (Desktop app) as client_secret.json
2. pip install google-auth-oauthlib
3. python auth_setup.py
4. Copy the 3 printed values into GitHub -> Settings -> Secrets and variables -> Actions
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
cfg = json.load(open("client_secret.json"))
c = cfg.get("installed") or cfg.get("web")
print("\nAdd these as GitHub Actions secrets:\n")
print("YT_CLIENT_ID     =", c["client_id"])
print("YT_CLIENT_SECRET =", c["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
print("\nNever commit client_secret.json or these values to the repo.")
