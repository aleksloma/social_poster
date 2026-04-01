# Social Poster

Automated social media posting service for [PowerDataChat](https://powerdatachat.com). Fetches blog posts from the PowerDataChat API, uses Google Gemini to generate platform-specific content, and publishes to LinkedIn, Facebook, and X (Twitter) on a configurable schedule.

## Features

- **Multi-platform**: Posts to LinkedIn, Facebook, and X with platform-optimized content
- **AI-generated content**: Uses Gemini 2.0 Flash with research-backed, platform-specific prompts tuned for optimal engagement (character counts, tone, structure)
- **Two-pass quality check**: Every generated post is validated by a second Gemini call that checks length, accuracy, tone, and hook quality — correcting issues automatically
- **Cross-platform differentiation**: When the same blog post goes to multiple platforms, previously generated posts are fed as context so each platform gets a completely different angle
- **Image support**: Automatically attaches blog featured images to social posts; logs whether each post included an image
- **Configurable schedule**: Set posting days, times, and frequency per platform in `config.yaml`
- **Idempotent**: SQLite database tracks posted content — no duplicate posts
- **Graceful degradation**: Missing API keys skip that platform without errors
- **Retry logic**: Network failures retry once before logging and continuing

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.template .env
```

Edit `.env` and fill in the API keys for the platforms you want to use. Any platform with missing keys will be skipped automatically.

**Required for content generation:**
- `GEMINI_API_KEY` — Get from [Google AI Studio](https://aistudio.google.com/apikey)

**Platform credentials (all optional — skip any you don't need):**
- LinkedIn: Run `python auth_helpers/linkedin_oauth.py` to get OAuth tokens
- Facebook: Run `python auth_helpers/facebook_token.py` to get page tokens
- X/Twitter: Create an app at [developer.x.com](https://developer.x.com) and get OAuth 1.0a keys

### 3. Run

```bash
# Single cycle (fetch, generate, publish, exit)
python main.py --once

# Dry run (generate content, print to console, don't publish)
python main.py --dry-run

# Continuous mode (runs every 6 hours)
python main.py
```

## Configuration

Edit `config.yaml` to customize the posting schedule:

```yaml
schedule:
  linkedin:
    posts_per_week: 2
    days: [1, 3]         # Tuesday, Thursday (0=Monday)
    post_hour_utc: 14

  facebook:
    posts_per_week: 3
    days: [0, 2, 4]      # Monday, Wednesday, Friday
    post_hour_utc: 16

  x:
    posts_per_week: 2
    days: [1, 4]          # Tuesday, Friday
    post_hour_utc: 15
```

## Project Structure

```
social-poster/
├── main.py              # Entry point — orchestrates fetch → generate → publish
├── config.py            # Loads config.yaml and .env
├── config.yaml          # Schedule settings, posting days/times
├── db.py                # SQLite — tracks which posts were sent where
├── blog_fetcher.py      # Calls PowerDataChat API, returns new posts
├── content_generator.py # Calls Gemini API with platform-specific prompts
├── publishers/
│   ├── linkedin.py      # LinkedIn API client with image upload
│   ├── facebook.py      # Facebook Graph API client
│   └── twitter.py       # X/Twitter API client with OAuth 1.0a
├── scheduler.py         # Distributes posts across platforms
├── auth_helpers/
│   ├── linkedin_oauth.py   # Interactive OAuth helper
│   └── facebook_token.py   # Interactive token helper
├── tests/               # pytest test suite
├── Dockerfile
├── deploy_gcp.sh        # GCP Cloud Run Job deployment
├── .env.template        # Credential template
└── requirements.txt
```

## Testing

```bash
pytest tests/ -v
```

## GCP Deployment

Deploys as a Cloud Run **Job** (not Service), triggered every 6 hours by Cloud Scheduler.

```bash
chmod +x deploy_gcp.sh
./deploy_gcp.sh
```

The deploy script:
1. Builds a container image
2. Creates secrets in Secret Manager (prefixed with `SOCIAL_POSTER_`)
3. Deploys a Cloud Run Job named `social-poster`
4. Sets up Cloud Scheduler to trigger it every 6 hours

**Important:** This is completely isolated from the main PowerDataChat (`datachat`) service. It uses separate secrets, a separate container image, and a separate Cloud Run Job.

## How It Works

1. **Fetch**: Pulls the latest blog posts from `powerdatachat.com/api/blog/posts`
2. **Schedule**: Distributes posts round-robin across platforms based on weekly quotas
3. **Generate**: Sends blog content to Gemini with platform-specific prompts optimized for each platform's engagement data (LinkedIn: 1,300-1,600 chars, Facebook: under 100 words, X: under 200 chars)
4. **Validate**: Each generated post goes through a second Gemini call that checks length, accuracy, tone, hook quality, and uniqueness — auto-correcting if needed
5. **Differentiate**: When the same blog goes to multiple platforms, each generation includes the other platforms' posts as context to ensure different angles
6. **Publish**: Posts to each platform's API with the featured image attached
7. **Track**: Records everything in SQLite to prevent duplicates

## Auth Helper Scripts

### LinkedIn OAuth

```bash
python auth_helpers/linkedin_oauth.py
```

Prerequisites:
- Create a LinkedIn App at [linkedin.com/developers](https://www.linkedin.com/developers/)
- Add redirect URL: `http://localhost:9999/callback` (Auth tab -> Authorized redirect URLs)
- Set `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` in `.env`

### Facebook Page Token

```bash
python auth_helpers/facebook_token.py
```

Prerequisites:
- Create a Facebook App at [developers.facebook.com](https://developers.facebook.com/)
- Add Facebook Login product with redirect: `http://localhost:8000/callback`
- Set `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET` in `.env`
