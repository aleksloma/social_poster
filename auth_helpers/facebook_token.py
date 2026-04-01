"""Interactive helper script to obtain a Facebook Page access token.

Prerequisites:
1. Create a Facebook App at https://developers.facebook.com/
2. Add the Facebook Login product
3. Set redirect URI to: http://localhost:8000/callback
4. Required permissions: pages_manage_posts, pages_read_engagement

Usage:
    python auth_helpers/facebook_token.py

This will:
1. Open your browser to Facebook's authorization page
2. Start a local server to catch the callback
3. Exchange the short-lived token for a long-lived token
4. List your pages and let you pick one
5. Get the page access token
6. Print credentials to add to your .env file
"""

import http.server
import os
import sys
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.environ.get("FACEBOOK_APP_ID", "")
APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "")
REDIRECT_URI = "http://localhost:8000/callback"
SCOPES = "pages_manage_posts,pages_read_engagement"

AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
GRAPH_URL = "https://graph.facebook.com/v19.0"


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this window.</p>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())

    def log_message(self, format, *args):
        pass


def main():
    if not APP_ID or not APP_SECRET:
        print("ERROR: Set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET in your .env file first.")
        sys.exit(1)

    # Step 1: Open browser for authorization
    auth_params = urllib.parse.urlencode({
        "client_id": APP_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "response_type": "code",
    })
    auth_full_url = f"{AUTH_URL}?{auth_params}"

    print("Opening browser for Facebook authorization...")
    print(f"URL: {auth_full_url}\n")
    webbrowser.open(auth_full_url)

    # Step 2: Catch callback
    print("Waiting for callback on http://localhost:8000/callback ...")
    server = http.server.HTTPServer(("localhost", 8000), CallbackHandler)
    server.handle_request()

    if not CallbackHandler.auth_code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    print("Authorization code received!")

    # Step 3: Exchange code for short-lived user token
    token_params = {
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": CallbackHandler.auth_code,
    }
    resp = requests.get(TOKEN_URL, params=token_params, timeout=30)
    resp.raise_for_status()
    short_token = resp.json()["access_token"]

    # Step 4: Exchange for long-lived token
    long_params = {
        "grant_type": "fb_exchange_token",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "fb_exchange_token": short_token,
    }
    resp = requests.get(TOKEN_URL, params=long_params, timeout=30)
    resp.raise_for_status()
    long_token = resp.json()["access_token"]
    print("Long-lived user token obtained!")

    # Step 5: List pages
    pages_url = f"{GRAPH_URL}/me/accounts"
    resp = requests.get(pages_url, params={"access_token": long_token}, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("data", [])

    if not pages:
        print("ERROR: No Facebook Pages found. Make sure your account manages at least one page.")
        sys.exit(1)

    print("\nYour Facebook Pages:")
    for i, page in enumerate(pages):
        print(f"  [{i}] {page['name']} (ID: {page['id']})")

    if len(pages) == 1:
        choice = 0
    else:
        choice = int(input("\nSelect a page number: "))

    selected = pages[choice]
    page_id = selected["id"]
    page_token = selected["access_token"]

    print("\n" + "=" * 60)
    print("Add these to your .env file:")
    print("=" * 60)
    print(f"FACEBOOK_PAGE_ID={page_id}")
    print(f"FACEBOOK_PAGE_ACCESS_TOKEN={page_token}")
    print("=" * 60)
    print(f"\nPage: {selected['name']}")
    print("Note: Long-lived page tokens don't expire if derived from a long-lived user token.")


if __name__ == "__main__":
    main()
