import os
import json
import random
import urllib.parse
import subprocess
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

NICHE = "Dark Psychology and Mind-Blowing Human Facts"
VOICE = "en-US-ChristopherNeural"

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

def generate_content():
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    Create a viral YouTube Short about: {NICHE}.
    Return ONLY valid JSON with these exact keys:
    - "title": catchy viral title under 65 characters including #shorts
    - "description": short engaging description with 5 relevant hashtags
    - "script": 90 to 110 words spoken script. Start with a strong curiosity hook in sentence 1. Short punchy sentences. No emojis, no stage directions, plain spoken English only.
    - "image_prompts": list of 5 detailed, dark, moody, cinematic vertical art prompts matching the story (no text inside images).
    """
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    res = requests.post(url, json=payload, timeout=60)
    res.raise_for_status()
    text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)

def create_voice_and_subs(script):
    subprocess.run([
        "edge-tts", "--voice", VOICE, "--text", script,
        "--write-media", "voice.mp3", "--write-subtitles", "subs.vtt"
    ], check=True)
    dur = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", "voice.mp3"
    ]).decode().strip()
    return float(dur)

def download_images(prompts):
    files = []
    for i, p in enumerate(prompts):
        encoded = urllib.parse.quote(f"{p}, vertical 9:16, ultra detailed, cinematic lighting")
        seed = random.randint(1, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}"
        img_name = f"img_{i}.jpg"
        r = requests.get(url, timeout=90)
        if r.status_code == 200:
            with open(img_name, "wb") as f:
                f.write(r.content)
            files.append(img_name)
    if not files:
        raise RuntimeError("No images downloaded.")
    return files

def build_video(images, total_duration):
    per_img = total_duration / len(images)
    frames = int(per_img * 30) + 10
    with open("concat.txt", "w") as cf:
        for i, img in enumerate(images):
            clip = f"clip_{i}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", img,
                "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.001,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30",
                "-t", f"{per_img:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", clip
            ], check=True)
            cf.write(f"file '{clip}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
        "-i", "voice.mp3",
        "-vf", "subtitles=subs.vtt:force_style='Fontsize=18,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,Outline=2,Alignment=10'",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", "output.mp4"
    ], check=True)

def upload_to_youtube(title, description):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
    )
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False
        }
    }
    media = MediaFileUpload("output.mp4", chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    res = req.execute()
    print("Uploaded Video ID:", res["id"])

if __name__ == "__main__":
    data = generate_content()
    print("Title:", data["title"])
    duration = create_voice_and_subs(data["script"])
    imgs = download_images(data["image_prompts"])
    build_video(imgs, duration)
    upload_to_youtube(data["title"], data["description"])
