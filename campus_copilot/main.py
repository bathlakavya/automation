import argparse
import json
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from . import llm, notify, pipeline, store


def load_cfg():
    with open(store.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_pa(cfg, text):
    """Personal-assistant: natural language -> calendar event or Notion note."""
    now = datetime.now(ZoneInfo(cfg["timezone"])).isoformat()
    task = (f'TASK: Convert the request to JSON. Now={now}. Schema: {{"action":"calendar"|"note",'
            '"title":str,"start_iso":str|null,"duration_min":int,"body":str}. '
            "start_iso must be ISO-8601 with +05:30 offset.\nREQUEST: " + text)
    res = llm.parse_json(llm.execute(task, json_mode=True))
    if res["action"] == "calendar" and res.get("start_iso"):
        notify.calendar_event(res["title"], notify.parse_dt(res["start_iso"]),
                              res.get("duration_min", 30), res.get("body", ""), cfg["timezone"])
        return f"Calendar event created: {res['title']} at {res['start_iso']}"
    notify.notion(res["title"], res.get("body") or text)
    return f"Note saved: {res['title']}"


def main(argv=None):
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="campus_copilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="one-time Google login")
    sub.add_parser("run", help="full daily run (classroom + jobs)")
    sub.add_parser("classroom", help="classroom brief only")
    sub.add_parser("jobs", help="job digest only")
    sub.add_parser("remind", help="cheap 24h deadline nudge (no LLM)")
    sub.add_parser("telegram-poll", help="check Telegram messages and personal reminders")
    a = sub.add_parser("ask", help="coding / build help (local Ollama model)"); a.add_argument("question")
    s = sub.add_parser("study", help="notes | quiz | hints | plan")
    s.add_argument("mode", choices=["notes", "quiz", "hints", "plan"]); s.add_argument("text")
    assist = sub.add_parser("assist", help="answer a coding or study request and send it to configured channels")
    assist.add_argument("mode", choices=["coding", "study"])
    assist.add_argument("request")
    pa = sub.add_parser("pa", help="personal assistant: 'remind me to ... Friday 6pm'"); pa.add_argument("text")
    f = sub.add_parser("feedback", help="train job ranking"); f.add_argument("job_id"); f.add_argument("vote", choices=["up", "down"])
    args = p.parse_args(argv)
    cfg = load_cfg()

    if args.cmd == "auth":
        from .classroom import get_creds
        get_creds(); print("Google auth OK")
    elif args.cmd == "run":
        res, body = pipeline.run_daily(cfg); print(body); print(json.dumps(res, indent=2))
    elif args.cmd == "classroom":
        print(pipeline.classroom_section(cfg))
    elif args.cmd == "jobs":
        print(pipeline.jobs_section(cfg))
    elif args.cmd == "remind":
        print(pipeline.remind(cfg) or "Nothing due in 24h")
    elif args.cmd == "telegram-poll":
        print(json.dumps(pipeline.telegram_poll(cfg), indent=2))
    elif args.cmd == "ask":
        print(llm.hermes(llm.load_prompt("coder"), args.question))
    elif args.cmd == "study":
        print(llm.hermes(llm.load_prompt("study"), f"MODE: {args.mode}\n\n{args.text}"))
    elif args.cmd == "assist":
        prompt = "coder" if args.mode == "coding" else "study"
        answer = llm.hermes(llm.load_prompt(prompt), args.request)
        results = notify.broadcast("Campus Copilot — " + args.mode.title() + " help", answer)
        print(json.dumps(results, indent=2))
    elif args.cmd == "pa":
        print(cmd_pa(cfg, args.text))
    elif args.cmd == "feedback":
        key = store.find_job_key(args.job_id)
        if not key:
            sys.exit("Unknown job id")
        title, company = store.job_meta(key)
        store.save_feedback(key, title, company, 1 if args.vote == "up" else 0)
        print("Saved. Tomorrow's ranking will use this.")


if __name__ == "__main__":
    main()
