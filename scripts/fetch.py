"""Fetch new product recalls from the official CPSC API and store them as JSON.

- Uses only the Python standard library (nothing to install).
- For each NEW recall it asks Gemini (if GEMINI_API_KEY is set) for a short
  plain-English summary. If Gemini is missing or fails, the post is still
  published using only the official facts.
"""
import datetime
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "recalls"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
API = "https://www.saferproducts.gov/RestWebServices/Recall"
UA = "RecallAlertDesk/1.0 (+news aggregator; plain-English recall summaries)"


def http_json(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_recalls():
    start = (datetime.date.today() - datetime.timedelta(days=int(CONFIG["lookback_days"]))).isoformat()
    url = API + "?" + urllib.parse.urlencode({"format": "json", "RecallDateStart": start})
    last_err = None
    for attempt in range(3):
        try:
            data = http_json(url)
            if isinstance(data, list):
                return data
            raise ValueError("Unexpected response from CPSC API")
        except Exception as e:  # network hiccup: wait and retry
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Could not fetch recalls: {last_err}")


def names(items, key="Name"):
    return [i.get(key, "").strip() for i in (items or []) if i.get(key, "").strip()]


def fact_sheet(r):
    """Plain-text facts that the AI is allowed to use (and nothing else)."""
    products = []
    for p in r.get("Products") or []:
        bits = [p.get("Name", ""), p.get("Model", ""), p.get("NumberOfUnits", "")]
        products.append(" | ".join(b for b in bits if b))
    parts = [
        f"Title: {r.get('Title', '')}",
        f"Recall date: {r.get('RecallDate', '')[:10]}",
        f"Recall number: {r.get('RecallNumber', '')}",
        f"Products: {'; '.join(products)}",
        f"Description: {r.get('Description', '')}",
        f"Hazards: {'; '.join(names(r.get('Hazards')))}",
        f"Injuries: {'; '.join(names(r.get('Injuries')))}",
        f"Remedy: {'; '.join(names(r.get('Remedies')))}",
        f"Remedy options: {', '.join(names(r.get('RemedyOptions'), 'Option'))}",
        f"Sold at: {'; '.join(names(r.get('Retailers')))}",
        f"Consumer contact: {r.get('ConsumerContact', '')}",
    ]
    return "\n".join(parts)


def numbers_in(text):
    return {n.strip(".,").replace(",", "") for n in re.findall(r"\d[\d,.]*", text)} - {""}


def ask_gemini(facts):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = CONFIG.get("gemini_model", "gemini-2.5-flash")
    prompt = (
        "You write short, clear consumer-safety explainers. Using ONLY the official recall facts below, "
        "return JSON with two string fields:\n"
        '  "summary": 2-3 sentences in plain English (about 8th-grade reading level) saying what was recalled and why it is a problem.\n'
        '  "next_steps": 1-3 sentences saying what owners should do, based strictly on the Remedy and Remedy options facts.\n'
        "Rules: do NOT invent or change any model numbers, dates, quantities, prices, phone numbers, or web addresses. "
        "Do not add medical or legal advice. Do not mention things not in the facts. Do not copy sentences word for word; paraphrase.\n\n"
        "OFFICIAL FACTS:\n" + facts
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        resp = http_json(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
        summary, steps = str(out.get("summary", "")).strip(), str(out.get("next_steps", "")).strip()
        if not summary or not steps or len(summary) > 900 or len(steps) > 700:
            return None
        # Safety check: every number the AI wrote must exist in the official facts.
        if not numbers_in(summary + " " + steps) <= numbers_in(facts):
            print("  AI text contained a number not in the source; discarded.")
            return None
        return {"summary": summary, "next_steps": steps, "model": model}
    except Exception as e:
        print(f"  Gemini failed ({type(e).__name__}: {e}); publishing facts only.")
        return None


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    recalls = fetch_recalls()
    print(f"CPSC returned {len(recalls)} recalls.")
    known = {p.stem for p in DATA.glob("*.json")}
    new = [r for r in recalls if str(r.get("RecallID")) not in known]
    new.sort(key=lambda r: r.get("RecallDate", ""), reverse=True)
    new = new[: int(CONFIG["max_new_posts_per_run"])]
    print(f"{len(new)} new recalls to publish this run.")
    for r in new:
        rid = str(r["RecallID"])
        print(f"- {rid}: {r.get('Title', '')[:80]}")
        ai = ask_gemini(fact_sheet(r))
        (DATA / f"{rid}.json").write_text(
            json.dumps({"record": r, "ai": ai}, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(7)  # stay inside free-tier rate limits


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
