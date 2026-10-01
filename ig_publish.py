#!/usr/bin/env python3
"""Publish a reel to Instagram via the official Graph API (Route A).

Flow: POST /{ig_user_id}/media (REEL) -> poll /{media_id} -> POST /{ig_user_id}/media_publish
Token needs: instagram_content_publish + pages_show_list + pages_manage_metadata
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

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
        with urllib.request.urlopen(r, timeout=180) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        sys.exit(1)


def resolve_ig_user_id(page_id, token):
    r = req(f"{API}/{page_id}?fields=instagram_business_account", token)
    return r["instagram_business_account"]["id"]


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
    a = ap.parse_args()

    ig = resolve_ig_user_id(a.page_id, a.token)
    print(f"IG business account: {ig}")

    if not a.video:
        print("nothing to publish (pass --video PATH --caption TEXT)", file=sys.stderr)
        sys.exit(0)

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
