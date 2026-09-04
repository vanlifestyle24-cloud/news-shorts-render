import os
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
from googleapiclient.errors import HttpError

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]
TITLE = os.environ.get("VIDEO_TITLE", "Untitled Short").strip()[:100]
DESCRIPTION = os.environ.get("VIDEO_DESCRIPTION", "").strip()
HASHTAGS_TEXT = os.environ.get("HASHTAGS_TEXT", "#news #uk #shorts").strip()
TAGS = [t.strip() for t in os.environ.get("VIDEO_TAGS", "").split(",") if t.strip()]
PRIVACY_STATUS = os.environ.get("PRIVACY_STATUS", "private")

full_description = f"{DESCRIPTION}\n\n{HASHTAGS_TEXT}".strip()

creds = google.oauth2.credentials.Credentials(
    None,
    refresh_token=REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
)

youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

body = {
    "snippet": {
        "title": TITLE,
        "description": full_description,
        "tags": TAGS,
        "categoryId": "25",  # News & Politics
    },
    "status": {
        "privacyStatus": PRIVACY_STATUS,
        "selfDeclaredMadeForKids": False,
    },
}

media = googleapiclient.http.MediaFileUpload(
    "output.mp4", chunksize=-1, resumable=True, mimetype="video/mp4"
)

request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f"Uploaded {int(status.progress() * 100)}%")

video_id = response.get("id")
print("Upload complete. Video ID:", video_id)
print("Privacy status used:", PRIVACY_STATUS)

# Post an engagement comment on the freshly uploaded video.
# Note: the YouTube Data API has no "pin comment" endpoint - pinning still
# requires one manual click in YouTube Studio (Comments -> ... -> Pin).
try:
    youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": "Thanks for watching! What's your take on this story? Let us know below 👇"
                    }
                },
            }
        },
    ).execute()
    print("Posted first comment. Pin it manually in YouTube Studio if you'd like it pinned.")
except HttpError as e:
    print("Could not post first comment (check OAuth scope includes youtube.force-ssl):", e)
