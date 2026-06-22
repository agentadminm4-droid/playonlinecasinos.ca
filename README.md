# PlayOnlineCasinos.ca

Ontario's guide to live dealer games, slots, and table games at AGCO-licensed casinos.

## Stack

- **Static HTML/CSS/JS** — no build step, no framework
- **GitHub Pages** for hosting
- **Dark theme** — `#0a0e1a` background, gold accent (`#d4af37`)
- **Python generators** — `generate_pages.py`, `generate_content.py`, `generate_blog.py`, `generate_seo.py` build the site from templates

## Local development

```bash
# 1. Generate everything (run from this directory)
python3 generate_pages.py
python3 generate_content.py
python3 generate_blog.py
python3 generate_seo.py

# 2. Preview locally
python3 -m http.server 8785
# Open http://localhost:8785/
```

## Deploy

```bash
# 1. Sync source -> deploy dir (rsync is additive, no --delete)
rsync -a --exclude='generate_*.py' --exclude='__pycache__' \
  ~/Desktop/playonlinecasinos/ \
  ~/Desktop/playonlinecasinos-deploy/

# 2. Commit and push
cd ~/Desktop/playonlinecasinos-deploy
git add -A
git commit -m "content: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push origin main
```

## Directory structure

```
playonlinecasinos/
├── index.html              # Homepage
├── live-dealer/            # Live casino hub
├── slots/                  # Slots hub
├── table-games/            # Table games hub
├── reviews/                # Operator + game reviews
├── blog/                   # News + evergreen guides
├── providers/              # Game provider directory
├── about/                  # About page
├── contact/                # Contact page
├── privacy-policy/         # Legal
├── terms-of-service/       # Legal
├── affiliate-disclosure/   # Legal
├── responsible-gambling/   # Compliance
├── css/                    # Single dark-theme stylesheet
├── js/                     # Mobile nav toggle
├── images/                 # Game thumbnails, OG images
├── generate_*.py           # Page generators (not deployed)
├── sitemap.xml             # Auto-generated
├── feed.xml                # Auto-generated RSS
└── robots.txt
```

## Content sources

- Reviews and guides: written by hand, stored in `generate_*.py` templates
- News/evergreen blog: `generate_blog.py`
- Sitemap/RSS: `generate_seo.py` walks the directory tree

## Compliance

All casinos listed are AGCO-licensed and verified against the iGaming Ontario public registry. We do not accept payment in exchange for positive coverage. See `/responsible-gambling/` for help resources.
