import os
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]
TITLE = os.environ.get("VIDEO_TITLE", "Untitled Short")
DESCRIPTION = os.environ.get("VIDEO_DESCRIPTION", "")
TAGS = [t.strip() for t in os.environ.get("VIDEO_TAGS", "").split(",") if t.strip()]

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
        "description": DESCRIPTION + "\n\n#Shorts",
        "tags": TAGS,
        "categoryId": "25",  # News & Politics
    },
    "status": {
        "privacyStatus": "public",
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

print("Upload complete. Video ID:", response.get("id"))
