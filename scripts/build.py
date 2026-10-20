"""Build the static website into the /public folder from data/recalls/*.json."""
import datetime
import html
import json
import os
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "recalls"
OUT = ROOT / "public"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
NAME = CONFIG["site_name"]
e = html.escape


def read_optional(name):
    p = ROOT / "ads" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


ADS_HEAD = read_optional("head.html")
ADS_SLOT = read_optional("slot.html")

CSS = """
:root{--bg:#fff;--fg:#1c2330;--muted:#5b6678;--line:#e3e7ee;--card:#f6f8fb;--accent:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--fg:#e8ecf2;--muted:#9aa5b5;--line:#2a313c;--card:#1a2029;--accent:#ff8a80}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--accent)}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header.site{border-bottom:1px solid var(--line);padding:14px 0}
header.site .wrap{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;justify-content:space-between}
.brand{font-weight:800;font-size:1.25rem;color:var(--fg);text-decoration:none}
nav a{margin-right:14px;font-size:.95rem;color:var(--muted)}
h1{font-size:1.7rem;line-height:1.25;margin:1.2rem 0 .4rem}
h2{font-size:1.2rem;margin:1.6rem 0 .4rem}
.meta{color:var(--muted);font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.list{list-style:none;padding:0;margin:0}
.list li{padding:14px 0;border-bottom:1px solid var(--line)}
.list a.t{font-weight:700;font-size:1.05rem;text-decoration:none;color:var(--fg)}
.list a.t:hover{text-decoration:underline}
.notice{font-size:.88rem;color:var(--muted);border-left:3px solid var(--line);padding-left:12px;margin:18px 0}
table{border-collapse:collapse;width:100%;font-size:.95rem}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
footer{border-top:1px solid var(--line);margin-top:40px;padding:20px 0;color:var(--muted);font-size:.88rem}
.ad{margin:18px 0;text-align:center}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:600}
"""


def layout(title, desc, body, depth, path, extra_head=""):
    pre = "../" * depth
    canon = f'<link rel="canonical" href="{e(SITE_URL + path)}">' if SITE_URL else ""
    full_title = f"{title} | {NAME}" if title != NAME else NAME
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
{canon}
<link rel="alternate" type="application/rss+xml" title="{e(NAME)}" href="{pre}feed.xml">
<link rel="stylesheet" href="{pre}style.css">
{ADS_HEAD}{extra_head}
</head><body>
<header class="site"><div class="wrap">
<a class="brand" href="{pre or './'}">{e(NAME)}</a>
<nav><a href="{pre}">Latest</a><a href="{pre}archive/">Archive</a><a href="{pre}about/">About</a></nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
<p>{e(NAME)} is an independent information site. It is <strong>not</strong> a government website and is not affiliated with the U.S. Consumer Product Safety Commission. Always confirm details on the official notice before acting.</p>
<p><a href="{pre}about/">About</a> · <a href="{pre}disclaimer/">Disclaimer</a> · <a href="{pre}privacy/">Privacy Policy</a> · <a href="{pre}contact/">Contact</a> · <a href="{pre}feed.xml">RSS</a></p>
</div></footer>
</body></html>"""


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60].strip("-") or "recall"


def parse_date(s):
    try:
        return datetime.date.fromisoformat((s or "")[:10])
    except ValueError:
        return datetime.date.today()


def names(items, key="Name"):
    return [i.get(key, "").strip() for i in (items or []) if i.get(key, "").strip()]


def li_list(items):
    return "<ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>" if items else ""


def load_posts():
    posts = []
    for f in DATA.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        r = d["record"]
        date = parse_date(r.get("RecallDate"))
        slug = f"{r['RecallID']}-{slugify(r.get('Title', ''))}"
        posts.append({"r": r, "ai": d.get("ai"), "date": date, "slug": slug})
    posts.sort(key=lambda p: (p["date"], int(p["r"]["RecallID"])), reverse=True)
    return posts


def post_page(p):
    r, ai = p["r"], p["ai"]
    title = r.get("Title", "Product recall")
    url = r.get("URL", "")
    parts = [f"<h1>{e(title)}</h1>",
             f'<p class="meta">Recall date: {p["date"].strftime("%B %d, %Y").replace(" 0", " ")} · '
             f'CPSC recall number: {e(str(r.get("RecallNumber", "")))}</p>']
    if ai:
        parts.append(f'<div class="card"><strong>In plain English</strong><p>{e(ai["summary"])}</p>'
                     f'<strong>What to do</strong><p>{e(ai["next_steps"])}</p>'
                     '<p class="meta">Summary written with AI from the official notice below. '
                     'Check the official notice before acting.</p></div>')
    if ADS_SLOT:
        parts.append(f'<div class="ad">{ADS_SLOT}</div>')

    rows = []
    for pr in r.get("Products") or []:
        for label, key in (("Product", "Name"), ("Model", "Model"), ("Type", "Type"), ("Units affected", "NumberOfUnits")):
            if pr.get(key):
                rows.append(f"<tr><th>{label}</th><td>{e(pr[key])}</td></tr>")
    if rows:
        parts.append("<h2>What is recalled</h2><table>" + "".join(rows) + "</table>")
    if r.get("Description"):
        parts.append(f"<p>{e(r['Description'])}</p>")
    hz = names(r.get("Hazards"))
    if hz:
        parts.append("<h2>The hazard</h2>" + li_list(hz))
    inj = names(r.get("Injuries"))
    if inj:
        parts.append("<h2>Reported incidents and injuries</h2>" + li_list(inj))
    rem = names(r.get("Remedies"))
    opts = names(r.get("RemedyOptions"), "Option")
    if rem or opts:
        parts.append("<h2>What you should do</h2>" + li_list(rem))
        if opts:
            parts.append(f"<p><strong>Remedy offered:</strong> {e(', '.join(opts))}</p>")
    sold = names(r.get("Retailers"))
    if sold:
        parts.append("<h2>Where it was sold</h2>" + li_list(sold))
    makers = names(r.get("Manufacturers")) + names(r.get("Importers")) + names(r.get("Distributors"))
    if makers:
        parts.append("<h2>Company</h2>" + li_list(makers))
    if r.get("ConsumerContact"):
        parts.append(f"<h2>Contact the company</h2><p>{e(r['ConsumerContact'])}</p>")
    if url.startswith("https://"):
        parts.append(f'<p><a class="btn" href="{e(url)}" rel="noopener">Read the official CPSC notice</a></p>')
    parts.append('<p class="notice">Source: U.S. Consumer Product Safety Commission (cpsc.gov). '
                 'Details above come from the official notice; recall details can be updated by the agency.</p>')
    desc = (ai["summary"] if ai else r.get("Description", title))[:155]
    return layout(title, desc, "\n".join(parts), 2, f"/recalls/{p['slug']}/")


def post_list(posts, depth):
    pre = "../" * depth
    items = []
    for p in posts:
        items.append(
            f'<li><a class="t" href="{pre}recalls/{p["slug"]}/">{e(p["r"].get("Title", ""))}</a>'
            f'<div class="meta">{p["date"].strftime("%b %d, %Y").replace(" 0", " ")}</div></li>')
    return '<ul class="list">' + "".join(items) + "</ul>"


def write(path, content):
    f = OUT / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")


def static_pages():
    contact = CONFIG.get("contact_email", "").strip()
    contact_line = (f'<p>Email: <a href="mailto:{e(contact)}">{e(contact)}</a></p>' if contact
                    else "<p>Contact email not set yet. The site owner can add it in config.json.</p>")
    return {
        "about": ("About", f"""<h1>About {e(NAME)}</h1>
<p>{e(NAME)} publishes short, plain-English summaries of product recalls announced by the U.S. Consumer Product Safety Commission (CPSC).
Government recall notices can be long and hard to scan, so each post here lists the essentials: what was recalled, the hazard, what to do, where it was sold, and a link to the official notice.</p>
<h2>How posts are made</h2>
<p>New recalls are collected automatically from the CPSC's public recall data. Each post shows the official facts, and an AI tool may add a short plain-English summary written only from those facts. AI can make mistakes, so please always confirm details, including model numbers and instructions, on the official notice linked in every post.</p>
<h2>What we are not</h2>
<p>We are not a government agency and we do not sell recalled products. We cannot process refunds or replacements; contact the company named in each post.</p>"""),
        "disclaimer": ("Disclaimer", f"""<h1>Disclaimer</h1>
<p>The information on {e(NAME)} is provided for general information only. It is not professional, medical, or legal advice. Recall details come from official government notices and can change. Summaries may contain errors. Before acting, always check the official notice linked in each post and follow the company's and agency's instructions.</p>
<p>{e(NAME)} is not affiliated with, endorsed by, or connected to the U.S. Consumer Product Safety Commission or any company named in a recall.</p>"""),
        "privacy": ("Privacy Policy", f"""<h1>Privacy Policy</h1>
<p>{e(NAME)} does not ask visitors to create accounts or submit personal information.</p>
<h2>Cookies and advertising</h2>
<p>This site may display ads from third-party advertising networks (for example Google AdSense or Adsterra). These partners may use cookies or similar technologies to show ads based on your visits to this and other websites. You can learn about and manage personalized advertising through your browser settings and tools such as <a href="https://www.aboutads.info/choices/" rel="noopener">aboutads.info/choices</a>.</p>
<h2>Server logs</h2>
<p>Our hosting provider may collect standard technical logs such as IP address and browser type for security and operations.</p>
<h2>Links to other sites</h2>
<p>Posts link to official government and company websites. We are not responsible for their privacy practices.</p>"""),
        "contact": ("Contact", f"""<h1>Contact</h1>
<p>Found a mistake, or want a post corrected? Please tell us and include the link to the post.</p>
{contact_line}"""),
    }


def rfc822(d):
    return datetime.datetime(d.year, d.month, d.day, 12, 0).strftime("%a, %d %b %Y %H:%M:%S +0000")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    write("style.css", CSS)
    posts = load_posts()

    n = int(CONFIG["homepage_post_count"])
    if posts:
        home_body = (f'<h1>{e(NAME)}</h1><p class="meta">{e(CONFIG["tagline"])}</p>'
                     + (f'<div class="ad">{ADS_SLOT}</div>' if ADS_SLOT else "")
                     + post_list(posts[:n], 0))
    else:
        home_body = f'<h1>{e(NAME)}</h1><p>{e(CONFIG["tagline"])}</p><p>No recalls published yet. Check back soon.</p>'
    write("index.html", layout(NAME, CONFIG["tagline"], home_body, 0, "/"))

    write("archive/index.html", layout("Recall archive", f"All product recalls published on {NAME}.",
                                       "<h1>Recall archive</h1>" + post_list(posts, 1), 1, "/archive/"))
    for p in posts:
        write(f"recalls/{p['slug']}/index.html", post_page(p))
    for slug, (title, body) in static_pages().items():
        write(f"{slug}/index.html", layout(title, f"{title} for {NAME}.", body, 1, f"/{slug}/"))

    # sitemap + robots + RSS (only when the public address is known)
    if SITE_URL:
        urls = ["/", "/archive/", "/about/", "/disclaimer/", "/privacy/", "/contact/"] + [f"/recalls/{p['slug']}/" for p in posts]
        write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
              + "\n".join(f"<url><loc>{e(SITE_URL + u)}</loc></url>" for u in urls) + "\n</urlset>\n")
        write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    else:
        write("robots.txt", "User-agent: *\nAllow: /\n")
    items = "".join(
        f"<item><title>{e(p['r'].get('Title', ''))}</title>"
        f"<link>{e(SITE_URL + '/recalls/' + p['slug'] + '/')}</link>"
        f"<guid>{e(SITE_URL + '/recalls/' + p['slug'] + '/')}</guid>"
        f"<pubDate>{rfc822(p['date'])}</pubDate></item>" for p in posts[:30])
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{e(NAME)}</title>'
          f"<link>{e(SITE_URL or '/')}</link><description>{e(CONFIG['tagline'])}</description>{items}</channel></rss>\n")
    write(".nojekyll", "")
    print(f"Built {len(posts)} recall posts into {OUT}")


if __name__ == "__main__":
    main()
