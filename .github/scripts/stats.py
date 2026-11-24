"""Draws assets for the profile README from the GitHub API (stdlib only).

    GITHUB_TOKEN=... python stats.py <user> <out.svg>
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      contributionCalendar { totalContributions weeks { contributionDays { contributionCount date } } }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
  }
}"""

FONT = "font-family=\"'Instrument Sans', Inter, 'Segoe UI', system-ui, sans-serif\""


def fetch(login, token):
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
                                 headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]


def summarize(user):
    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cc["contributionCalendar"]["weeks"]]
    # current streak: today may still be empty, so it doesn't break the streak
    streak = 0
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"]:
            streak += 1
        elif i > 0:
            break
    langs = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            size, color = langs.get(n, (0, e["node"]["color"] or "#8a8a96"))
            langs[n] = (size + e["size"], color)
    top = sorted(langs.items(), key=lambda x: -x[1][0])[:6]
    total = sum(s for _, (s, _) in top) or 1   # share among the top 6, so the bar fills up
    return {
        "contributions": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in user["repositories"]["nodes"]),
        "streak": streak,
        "weeks": weeks[-52:],
        "langs": [(n, s / total, c) for n, (s, c) in top],
    }


def svg(s):
    W, H = 880, 250
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           '<defs><linearGradient id="f" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1a1a20"/>'
           '<stop offset="1" stop-color="#131317"/></linearGradient></defs>',
           f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="url(#f)" stroke="#ffffff" stroke-opacity="0.08"/>',
           f'<g {FONT}>']
    # numbers
    nums = [("contributions", "contributions"), ("commits", "commits"), ("streak", "day streak"), ("repos", "public repos")]
    for i, (k, label) in enumerate(nums):
        x = 32 + i * 105
        out.append(f'<text x="{x}" y="64" font-size="30" font-weight="600" fill="#ececf1">{s[k]}</text>'
                   f'<text x="{x}" y="86" font-size="12.5" fill="#8a8a96">{label}</text>')
    # weekly activity, bars rise one after another
    peak = max(s["weeks"]) or 1
    bw, gap, x0, base = 6, 2, 32, 214
    out.append(f'<text x="{x0}" y="124" font-size="12.5" fill="#8a8a96">last 12 months, week by week</text>')
    for i, v in enumerate(s["weeks"]):
        h = max(2, v / peak * 70)
        op = 0.25 + 0.75 * (v / peak)
        out.append(f'<rect x="{x0 + i * (bw + gap)}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="2" fill="#9db4ff" '
                   f'fill-opacity="{op:.2f}"><animate attributeName="height" from="0" to="{h:.1f}" dur="0.6s" '
                   f'begin="{i * 0.02:.2f}s" fill="freeze"/><animate attributeName="y" from="{base}" to="{base - h:.1f}" '
                   f'dur="0.6s" begin="{i * 0.02:.2f}s" fill="freeze"/></rect>')
    # languages
    lx, lw = 500, 348
    out.append(f'<line x1="476" y1="32" x2="476" y2="{H - 32}" stroke="#ffffff" stroke-opacity="0.06"/>'
               f'<text x="{lx}" y="52" font-size="12.5" fill="#8a8a96">most used languages</text>'
               f'<clipPath id="bar"><rect x="{lx}" y="66" width="{lw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    x = lx
    for _, frac, color in s["langs"]:
        w = frac * lw
        out.append(f'<rect x="{x:.1f}" y="66" width="{w + 0.5:.1f}" height="10" fill="{color}"/>')
        x += w
    out.append('</g>')
    for i, (name, frac, color) in enumerate(s["langs"]):
        cx, cy = lx + (i % 2) * 178, 112 + (i // 2) * 34
        out.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>'
                   f'<text x="{cx + 18}" y="{cy}" font-size="14" fill="#c9c9d3">{escape(name)}</text>'
                   f'<text x="{cx + 166}" y="{cy}" font-size="13" fill="#5d5d6a" text-anchor="end">{frac * 100:.1f}%</text>')
    out.append(f'<text x="{W - 32}" y="{H - 20}" font-size="11" fill="#45454f" text-anchor="end">'
               f'updated {dt.date.today().isoformat()}</text></g></svg>')
    return "\n".join(out)


if __name__ == "__main__":
    login, dest = sys.argv[1], sys.argv[2]
    data = summarize(fetch(login, os.environ["GITHUB_TOKEN"]))
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w") as f:
        f.write(svg(data))
    print(json.dumps({k: v for k, v in data.items() if k != "weeks"}))
