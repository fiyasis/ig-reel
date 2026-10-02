#!/usr/bin/env python3
"""Publish a reel to Instagram (and optionally the linked Facebook Page) via the official Graph API.

IG flow:  POST /{ig_user_id}/media (REEL) -> poll /{container} -> POST /{ig_user_id}/media_publish
FB flow:  GET  /{page_id}?fields=access_token  ->  POST /{page_id}/videos (multipart)
Token needs: instagram_content_publish + pages_show_list + pages_manage_metadata (+ pages_manage_posts for FB video)
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = "https://graph.facebook.com/v23.0"


def req(url, token, data=None, method=None):
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode()
        else:
            body = data
        headers["content-type"] = "application/x-www-form-urlencoded"
    r = urllib.request.Request(url, data=body, headers=headers, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        sys.exit(1)


def multipart(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    ctype = mimetypes.guess_type(file_path)[0] or "video/mp4"
    fname = os.path.basename(file_path)
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{fname}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    with open(file_path, "rb") as f:
        out += f.read()
    out += f"\r\n--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def req_multipart(url, token, body, ctype, timeout=600):
    r = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {token}", "content-type": ctype})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        sys.exit(1)


def resolve_ig_user_id(page_id, token):
    r = req(f"{API}/{page_id}?fields=instagram_business_account", token)
    return r["instagram_business_account"]["id"]


def get_page_token(page_id, user_token):
    r = req(f"{API}/{page_id}?fields=access_token", user_token)
    return r["access_token"]


def publish_fb(page_id, user_token, video_path, caption):
    page_token = get_page_token(page_id, user_token)
    body, ctype = multipart({"message": caption}, "video_file", video_path)
    r = req_multipart(f"{API}/{page_id}/videos", page_token, body, ctype)
    print(f"FB PUBLISHED: https://www.facebook.com/{page_id}/videos/{r['id']}/")
    return r["id"]


def find_media_for_container(container, token):
    r = req(f"{API}/{container}/children?fields=id,media_type,status", token)
    for it in r.get("data", []):
        if it.get("status") == "FINISHED":
            return it["id"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page-id", required=True)
    ap.add_argument("--token", required=True, help="long-lived user token (NOT the FB page token)")
    ap.add_argument("--container", help="media container id from /media upload")
    ap.add_argument("--video")
    ap.add_argument("--caption", default="")
    ap.add_argument("--post-to-fb", action="store_true", help="also publish the same video to the linked Facebook Page")
    ap.add_argument("--fb-only", action="store_true", help="skip Instagram, post to the Facebook Page only")
    a = ap.parse_args()

    if not a.video:
        print("nothing to publish (pass --video PATH --caption TEXT)", file=sys.stderr)
        sys.exit(0)

    if a.post_to_fb or a.fb_only:
        publish_fb(a.page_id, a.token, a.video, a.caption)
    if not a.fb_only:
        ig = resolve_ig_user_id(a.page_id, a.token)
        print(f"IG business account: {ig}")

        with open(a.video, "rb") as f:
            video = f.read()

        if not a.container:
            params = {
                "media_type": "REEL",
                "video_data": video,
                "share_to_feed": "false",
            }
            if a.caption:
                params["caption"] = a.caption
            r = req(f"{API}/{ig}/media", a.token, data=params)
            container = r["id"]
            print(f"container created: {container}")
        else:
            container = a.container

        r = req(f"{API}/{container}", a.token)
        status = r.get("status")
        if status != "FINISHED":
            print(f"container not ready (status={status}, progress={r.get('progress')}) — run --container {container} again later")
            sys.exit(1)

        media_id = find_media_for_container(container, a.token)
        if not media_id:
            print("no FINISHED media found in container children", file=sys.stderr)
            sys.exit(1)
        print(f"media id: {media_id}")

        pub = req(f"{API}/{ig}/media_publish", a.token, data={"creation_id": media_id})
        print(f"PUBLISHED: https://www.instagram.com/reel/{pub['id']}/")


if __name__ == "__main__":
    main()
