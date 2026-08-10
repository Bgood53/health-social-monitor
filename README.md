# Health Social Monitor

A daily email digest of health-policy conversation on **Substack**, **Reddit**, and **Bluesky**, focused on CDC, outbreaks, FDA, HHS, and vaccines.

You maintain one file (`config.yaml`). The script runs automatically every morning via GitHub Actions.

---

## Quick start: how to use it

### If you haven't set it up yet

Do these steps once (~20 minutes):

1. **Gmail app password** — Google Account → Security → App Passwords (see below)
2. **Push to GitHub** — create a repo and upload this folder
3. **Add GitHub secrets** — repo Settings → Secrets → Actions → add the 6 email secrets from the table below
4. **Run a test** — GitHub → Actions → **Daily Health Social Digest** → **Run workflow**
5. **Check your inbox** — you should get an email within a few minutes

**No Reddit developer app needed.** Reddit now requires approval for API access; this project uses Reddit's free RSS feeds instead.

### If it's already set up

Your daily routine is simple:

| When | What to do |
|------|------------|
| **Every morning** | Read the email — no action needed |
| **When news breaks** | Edit `config.yaml` → add a keyword or Substack feed → push to GitHub |
| **To test immediately** | GitHub → Actions → Run workflow manually |
| **Something breaks** | Check the Actions tab for error logs |

### What's in each email

1. **Substack** — new posts from newsletters you follow (expert long-form takes)
2. **Reddit** — recent posts from health subreddits matching your keywords
3. **Bluesky** — recent posts from keyword searches across the network

Each item has a title, author, timestamp, short snippet, and a clickable link.

---

## What you get

Each morning you'll receive an email with three sections:

1. **Substack** — new posts from health-policy newsletters you follow
2. **Reddit** — recent posts from health-related subreddits that match your keywords
3. **Bluesky** — recent posts from keyword searches across the network

Each item includes the title/text, author, source, timestamp, and a direct link.

---

## One-time setup

### 1. Set up email (Gmail example)

Gmail requires an **App Password** (not your normal password):

1. Enable 2-factor authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create an app password for "Mail"
4. Use that 16-character password as `SMTP_PASSWORD`

If you use work email via another provider, ask IT for SMTP settings or use a Gmail account just for sending digests.

### 2. Push to GitHub and add secrets

```bash
cd ~/Projects/health-social-monitor
git init
git add .
git commit -m "Initial health social monitor setup"
```

Create a new repo on GitHub, push it, then add these **Repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Example value |
|--------|----------------|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASSWORD` | Gmail app password |
| `EMAIL_FROM` | same as SMTP_USER |
| `EMAIL_TO` | where you want the digest delivered |

**Optional** (recommended — makes Reddit fetching faster):

| Secret | Example value |
|--------|----------------|
| `REDDIT_RSS_USER` | your Reddit username |
| `REDDIT_RSS_FEED` | token from reddit.com/prefs/feeds |

### 3. Optional: Reddit RSS feed token (recommended)

Reddit limits anonymous RSS to about one request per minute. Since the digest checks several subreddits, adding your personal feed token avoids long waits.

1. Log into Reddit
2. Go to https://www.reddit.com/prefs/feeds
3. Copy the `user=` and `feed=` values from any feed URL shown there
4. Add them as GitHub secrets `REDDIT_RSS_USER` and `REDDIT_RSS_FEED`

Without these, the digest still works — it just pauses ~1 minute between each subreddit (fine for a once-daily email).

### 4. Test it

In GitHub: **Actions → Daily Health Social Digest → Run workflow**.

You should receive an email within a minute or two.

---

## How to maintain it (your only regular task)

Open **`config.yaml`** when your beat changes. You never need to edit Python code for normal use.

### Add keywords when news breaks

Example: a new measles outbreak story is dominating the cycle.

```yaml
beat:
  keywords:
    - CDC
    - outbreak
    - FDA
    - HHS
    - vaccine
    - vaccines
    - measles        # ← add this
    - "Texas measles" # ← phrases work too (use quotes)
```

Commit and push — the next scheduled run picks up the change automatically.

### Add or remove subreddits

```yaml
reddit:
  subreddits:
    - healthpolicy
    - epidemiology
    - publichealth
    - vaccines
    - nursing
    - coronavirus   # ← add when relevant
```

### Adjust volume

```yaml
limits:
  max_items_per_source: 25   # lower to 10 for a shorter digest
```

```yaml
reddit:
  lookback_hours: 24   # change to 48 for a weekend catch-up
```

### Add Substack newsletters

Every Substack has a free RSS feed. To find it, open any newsletter in your browser and add `/feed` to the URL:

```
https://yourlocalepidemiologist.substack.com/feed
```

Add it to `config.yaml`:

```yaml
substack:
  lookback_hours: 72          # newsletters publish less often than social posts
  filter_by_keywords: false   # false = all new posts; true = keyword matches only
  newsletters:
    - name: Your Local Epidemiologist
      feed: https://yourlocalepidemiologist.substack.com/feed
    - name: Another Newsletter
      feed: https://theirname.substack.com/feed
```

Replace the example newsletters with ones you actually read. Set `filter_by_keywords: true` if you only want Substack posts that mention CDC, FDA, etc.

---

## Test locally (optional)

```bash
cd ~/Projects/health-social-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your real credentials
export $(grep -v '^#' .env | xargs)
python digest.py
```

---

## Schedule

The digest runs at **7:00 AM Eastern** (11:00 UTC) on weekdays and weekends.

To change the time, edit `.github/workflows/daily-digest.yml`:

```yaml
- cron: "0 11 * * *"   # minute hour day month weekday (UTC)
```

Use https://crontab.guru to pick a new time.

---

## What's not covered yet

| Platform | Status | Recommendation |
|----------|--------|----------------|
| **Substack** | Included (via RSS) | Add feed URLs in `config.yaml` |
| **X** | Not included | Can add later (API is paid) |
| **LinkedIn** | Not scriptable | Use saved searches or a listening tool |
| **Instagram / Facebook** | Not scriptable | Use Brandwatch/Talkwalker or manual monitoring |
| **GoFundMe** | Not scriptable | Set up [Google Alerts](https://www.google.com/alerts) for `site:gofundme.com` + your keywords |

---

## Troubleshooting

**No email received**
- Check GitHub Actions for a failed run (Actions tab)
- Verify all secrets are set correctly
- Check spam folder

**Too many irrelevant posts**
- Add more specific keywords or phrases in quotes
- Remove broad subreddits from the list
- Lower `max_items_per_source`

**Too few posts**
- Add subreddits or keywords
- Increase `lookback_hours` to 48

**Reddit rate-limit errors (HTTP 429)**
- Add `REDDIT_RSS_USER` and `REDDIT_RSS_FEED` secrets (see setup step 3)
- Or reduce the number of subreddits in `config.yaml`

**Reddit "Responsible Builder Policy" message**
- You can ignore the developer app process — this project no longer uses the Reddit API

---

## File overview

| File | Purpose | You edit? |
|------|---------|-----------|
| `config.yaml` | Keywords, subreddits, Substack feeds, limits | **Yes — regularly** |
| `digest.py` | Fetches posts and sends email | Rarely |
| `.github/workflows/daily-digest.yml` | Schedule | Only to change timing |
| `.env.example` | Template for local testing | No |
