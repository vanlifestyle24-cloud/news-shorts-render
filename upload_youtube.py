import os
import re
import sys
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
RAW_TAGS = os.environ.get("VIDEO_TAGS", "")
PRIVACY_STATUS = os.environ.get("PRIVACY_STATUS", "private")

# Set by the "Detect media orientation" step in render.yml. IS_SHORT is the
# real signal: YouTube itself decides Shorts vs normal video purely from the
# video's aspect ratio (vertical/square) and length - there's no API field
# to force it - so all we control here is keeping the #shorts tag honest:
# only claim "shorts" when the render actually came out vertical.
ORIENTATION = os.environ.get("ORIENTATION", "portrait").strip().lower()
IS_SHORT = os.environ.get("IS_SHORT", "true").strip().lower() == "true"


def strip_shorts_word(text):
    # remove any standalone "shorts"/"#shorts" token (case-insensitive)
    text = re.sub(r"#?\bshorts\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


if not IS_SHORT:
    # Landscape render -> this is a normal video, not a Short. Don't let a
    # leftover "shorts" hashtag/tag mislabel it.
    HASHTAGS_TEXT = strip_shorts_word(HASHTAGS_TEXT)
    RAW_TAGS = ",".join(t for t in RAW_TAGS.split(",") if t.strip().lower() != "shorts")
elif "shorts" not in RAW_TAGS.lower():
    RAW_TAGS = (RAW_TAGS + ",shorts").strip(",")

full_description = f"{DESCRIPTION}\n\n{HASHTAGS_TEXT}".strip()


def sanitize_tags(raw_tags_str, max_total_chars=460):
    """
    Turn a raw comma-separated tags string into a list that YouTube will
    actually accept. This is what was missing before and is what caused:
      googleapiclient.errors.ResumableUploadError: ... invalidTags ...

    YouTube rejects the WHOLE upload (not just the bad tag) if ANY of these
    are true:
      - a tag contains '<' or '>'
      - a tag is empty / only whitespace
      - the combined length of all tags (a tag with a space counts as
        len(tag)+2, as if it were quoted) exceeds ~500 characters
    We also strip stray '#' in case a hashtag slips through un-stripped,
    dedupe (case-insensitive), and cap each individual tag's length so one
    oversized/garbled tag from the AI script generator can't blow the
    whole budget.
    """
    cleaned = []
    seen = set()
    total_len = 0

    for raw in raw_tags_str.split(","):
        tag = raw.strip()
        if not tag:
            continue

        tag = tag.replace("#", "").replace("<", "").replace(">", "").strip()
        if not tag:
            continue

        tag = tag[:100]

        key = tag.lower()
        if key in seen:
            continue

        tag_len = len(tag) + (2 if re.search(r"\s", tag) else 0)
        if total_len + tag_len > max_total_chars:
            break

        cleaned.append(tag)
        seen.add(key)
        total_len += tag_len

    return cleaned


TAGS = sanitize_tags(RAW_TAGS)
print(f"Orientation: {ORIENTATION} | IS_SHORT: {IS_SHORT}")
print(f"Raw VIDEO_TAGS input: {RAW_TAGS!r}")
print(f"Sanitized tags being sent to YouTube ({len(TAGS)}): {TAGS}")

creds = google.oauth2.credentials.Credentials(
    None,
    refresh_token=REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
)

youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def build_body(tags):
    return {
        "snippet": {
            "title": TITLE,
            "description": full_description,
            "tags": tags,
            "categoryId": "25",  # News & Politics
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }


def upload(tags):
    media = googleapiclient.http.MediaFileUpload(
        "output.mp4", chunksize=-1, resumable=True, mimetype="video/mp4"
    )
    request = youtube.videos().insert(
        part="snippet,status", body=build_body(tags), media_body=media
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
    return response


try:
    response = upload(TAGS)
except HttpError as e:
    reason = ""
    try:
        reason = e.error_details[0].get("reason", "") if e.error_details else ""
    except Exception:
        pass

    if reason == "invalidTags" and TAGS:
        print(f"YouTube rejected tags {TAGS} (invalidTags). Retrying with no tags...")
        try:
            response = upload([])
        except HttpError as e2:
            print("Retry without tags also failed:", e2)
            sys.exit(1)
    else:
        print("Upload failed:", e)
        sys.exit(1)

video_id = response.get("id")
print("Upload complete. Video ID:", video_id)
print("Privacy status used:", PRIVACY_STATUS)
print("Rendered as:", "Short (vertical)" if IS_SHORT else "Regular video (landscape)")

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
