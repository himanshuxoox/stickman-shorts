"""
Upload a day's batch to YouTube, each scheduled to a different time slot.

    python -m shorts.upload --date 2026-10-02            # real upload
    python -m shorts.upload --date 2026-10-02 --dry-run  # just print the plan

Needs env vars (GitHub secrets): YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Get the refresh token once with:  python auth_setup.py

NOTE: until your Google Cloud project passes the YouTube API audit, YouTube
locks every API upload to PRIVATE. Keep AUTO_UPLOAD off until then and upload
the rendered files manually from YouTube Studio.
"""
import argparse, datetime as dt, json, os, sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = ZoneInfo("Asia/Kolkata")
# publish slots (IST) — override with env PUBLISH_SLOTS="08:30,12:30,17:30,21:00"
SLOTS = os.environ.get("PUBLISH_SLOTS", "08:30,12:30,17:30,21:00").split(",")


def plan_times(date_str, n):
    """Return n aware datetimes: today's remaining slots, spilling into tomorrow."""
    try:
        day = dt.date.fromisoformat(date_str)
    except ValueError:  # e.g. a "test" folder -> schedule from today
        day = dt.datetime.now(IST).date()
    now = dt.datetime.now(IST) + dt.timedelta(minutes=20)  # YouTube needs publishAt in future
    out, d = [], day
    while len(out) < n:
        for s in SLOTS:
            hh, mm = map(int, s.split(":"))
            t = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST)
            if t > now and len(out) < n:
                out.append(t)
        d += dt.timedelta(days=1)
    return out


def youtube_client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_one(yt, path, item, publish_at):
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {
            "title": item["title"],
            "description": item["description"],
            "tags": item["tags"],
            "categoryId": item.get("categoryId", "24"),
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",          # required for scheduled publishing
            "publishAt": publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selfDeclaredMadeForKids": False,
            # simulations: False; facts channel (AI images + AI voice): True
            "containsSyntheticMedia": bool(item.get("containsSyntheticMedia", False)),
        },
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _status, resp = req.next_chunk()
    return resp["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(IST).strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    day_dir = os.path.join(a.out, a.date)
    mpath = os.path.join(day_dir, "manifest.json")
    with open(mpath) as f:
        manifest = json.load(f)
    todo = [v for v in manifest["videos"] if not v.get("youtube_id")]
    times = plan_times(a.date, len(todo))

    yt = None if a.dry_run else youtube_client()
    for item, when in zip(todo, times):
        path = os.path.join(day_dir, item["file"])
        print(f"{when:%Y-%m-%d %H:%M IST}  {item['file']}  |  {item['title']}")
        if a.dry_run:
            continue
        try:
            vid = upload_one(yt, path, item, when)
        except Exception as e:  # keep going with the rest, report at the end
            print(f"   upload failed: {e}", file=sys.stderr)
            item["upload_error"] = str(e)
            continue
        item["youtube_id"] = vid
        item["publish_at"] = when.isoformat()
        print(f"   -> https://youtube.com/shorts/{vid}")

    if not a.dry_run:
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=1, ensure_ascii=False)
        if any("upload_error" in v for v in todo):
            sys.exit(1)


if __name__ == "__main__":
    main()
