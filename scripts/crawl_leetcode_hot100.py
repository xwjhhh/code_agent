"""Crawl the LeetCode China Hot 100 study plan into local JSON files.

The study-plan page provides the canonical 100-question ordering.  Each
question's full statement is fetched from LeetCode's public GraphQL endpoint.
The output is intentionally plain JSON so it can be consumed by later batch
generation scripts without another scraping pass.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PLAN_URL = "https://leetcode.cn/studyplan/top-100-liked/"
GRAPHQL_URL = "https://leetcode.cn/graphql/"
USER_AGENT = "Mozilla/5.0 (compatible; Hot100StudyPlanCrawler/1.0)"
QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    translatedTitle
    content
    translatedContent
    difficulty
    isPaidOnly
    topicTags { name translatedName slug }
    exampleTestcases
  }
}
"""


def fetch_bytes(url: str, *, payload: bytes | None = None, referer: str | None = None) -> bytes:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if payload is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(url, data=payload, headers=headers, method="POST" if payload else "GET")
    with urlopen(request, timeout=45) as response:
        return response.read()


def fetch_json(url: str, payload: dict[str, Any], *, referer: str) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    data = fetch_bytes(url, payload=body, referer=referer)
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GraphQL response is not a JSON object")
    return value


def parse_next_data(page: str) -> dict[str, Any]:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        page,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("Could not find __NEXT_DATA__ in study-plan page")
    value = json.loads(html.unescape(match.group(1)))
    if not isinstance(value, dict):
        raise RuntimeError("Invalid __NEXT_DATA__ payload")
    return value


def study_plan(data: dict[str, Any]) -> dict[str, Any]:
    try:
        return data["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["studyPlanV2Detail"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Study-plan structure changed; cannot locate question list") from error


def slug_filename(rank: int, question: dict[str, Any]) -> str:
    number = str(question.get("questionFrontendId") or rank).zfill(4)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(question.get("titleSlug") or "question"))
    return f"{rank:03d}-{number}-{slug}.json"


def fetch_question(slug: str) -> dict[str, Any]:
    last_error: Exception | None = None
    payload = {"query": QUESTION_QUERY, "variables": {"titleSlug": slug}}
    for attempt in range(1, 4):
        try:
            response = fetch_json(GRAPHQL_URL, payload, referer=f"https://leetcode.cn/problems/{slug}/")
            if response.get("errors"):
                raise RuntimeError(str(response["errors"]))
            question = response.get("data", {}).get("question")
            if not isinstance(question, dict):
                raise RuntimeError(f"No question data returned for {slug}")
            return question
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as error:
            last_error = error
            if attempt < 3:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"Failed to fetch {slug}: {last_error}")


def crawl(output_dir: Path, delay: float, workers: int) -> list[dict[str, Any]]:
    page = fetch_bytes(PLAN_URL).decode("utf-8")
    detail = study_plan(parse_next_data(page))
    groups = detail.get("planSubGroups")
    if not isinstance(groups, list):
        raise RuntimeError("Study plan contains no question groups")

    listed_questions: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or f"分组 {group_index}")
        group_slug = str(group.get("slug") or "")
        for group_item_index, listed in enumerate(group.get("questions", []), start=1):
            if not isinstance(listed, dict) or not listed.get("titleSlug"):
                continue
            listed_questions.append({
                "rank": len(listed_questions) + 1,
                "group_index": group_index,
                "group_item_index": group_item_index,
                "group_name": group_name,
                "group_slug": group_slug,
                "listed": listed,
            })

    if len(listed_questions) != 100:
        raise RuntimeError(f"Expected 100 questions in study plan, got {len(listed_questions)}")

    def fetch_item(entry: dict[str, Any]) -> dict[str, Any]:
        rank = int(entry["rank"])
        listed = entry["listed"]
        slug = str(listed["titleSlug"])
        print(f"[{rank:03d}/100] {listed.get('questionFrontendId', '?')} {listed.get('translatedTitle') or listed.get('title')}", flush=True)
        question = fetch_question(slug)
        tags = question.get("topicTags")
        normalized_tags = [
            {
                "name": str(tag.get("name", "")),
                "translated_name": str(tag.get("translatedName", "")),
                "slug": str(tag.get("slug", "")),
            }
            for tag in tags
            if isinstance(tag, dict)
        ] if isinstance(tags, list) else []
        item = {
                "rank": rank,
                "plan_slug": str(detail.get("slug") or "top-100-liked"),
                "plan_name": str(detail.get("name") or "LeetCode 热题 100"),
                "group_index": entry["group_index"],
                "group_item_index": entry["group_item_index"],
                "group_name": entry["group_name"],
                "group_slug": entry["group_slug"],
                "question_id": str(question.get("questionId") or listed.get("questionId") or ""),
                "frontend_id": str(question.get("questionFrontendId") or listed.get("questionFrontendId") or ""),
                "title": str(question.get("title") or listed.get("title") or ""),
                "translated_title": str(question.get("translatedTitle") or listed.get("translatedTitle") or ""),
                "title_slug": slug,
                "url": f"https://leetcode.cn/problems/{slug}/",
                "difficulty": str(question.get("difficulty") or listed.get("difficulty") or ""),
                "is_paid_only": bool(question.get("isPaidOnly", listed.get("isPaidOnly", False))),
                "topic_tags": normalized_tags,
                "content": question.get("content") or "",
                "translated_content": question.get("translatedContent") or "",
                "example_testcases": question.get("exampleTestcases") or "",
        }
        time.sleep(max(0.0, delay))
        return item

    fetched: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(fetch_item, entry) for entry in listed_questions]
        for future in as_completed(futures):
            item = future.result()
            fetched[int(item["rank"])] = item
    return [fetched[index] for index in range(1, 101)]


def write_output(output_dir: Path, questions: list[dict[str, Any]], scraped_at: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    question_dir = output_dir / "questions"
    question_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "questions.json").write_text(
        json.dumps({"source": PLAN_URL, "plan": "top-100-liked", "count": len(questions), "scraped_at": scraped_at, "questions": questions}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for question in questions:
        (question_dir / slug_filename(int(question["rank"]), question)).write_text(
            json.dumps(question, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    lines = [
        "# LeetCode 热题 100",
        "",
        f"来源：[力扣学习计划]({PLAN_URL})",
        f"抓取时间：`{scraped_at}`",
        "",
        "| 序号 | 题号 | 题目 | 难度 | 标签 |",
        "| ---: | ---: | --- | --- | --- |",
    ]
    for question in questions:
        tags = "、".join(tag["translated_name"] or tag["name"] for tag in question["topic_tags"])
        title = question["translated_title"] or question["title"]
        lines.append(
            f"| {question['rank']} | {question['frontend_id']} | [{title}]({question['url']}) | {question['difficulty']} | {tags} |"
        )
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(r"C:\Users\Administrator\Desktop\rebirth\面试\机试\力扣100"),
        help="directory receiving questions.json, README.md, and questions/",
    )
    parser.add_argument("--delay", type=float, default=0.2, help="seconds between GraphQL requests")
    parser.add_argument("--workers", type=int, default=5, help="parallel GraphQL requests (default: 5)")
    args = parser.parse_args()
    scraped_at = datetime.now(timezone.utc).isoformat()
    questions = crawl(args.output_dir, args.delay, args.workers)
    write_output(args.output_dir, questions, scraped_at)
    print(f"Wrote {len(questions)} questions to {args.output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
