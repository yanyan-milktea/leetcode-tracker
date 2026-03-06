import requests
import sqlite3
import sys
import time
from datetime import datetime, timezone
import pytz
from config import USERS, CN_USERS

DB_FILE = "tracker.db"

PACIFIC = pytz.timezone("US/Pacific")

LEETCODE_GLOBAL = "https://leetcode.com/graphql"
LEETCODE_CN = "https://leetcode.cn/graphql"

# ---------------- DB ----------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_records (
        username TEXT,
        date TEXT,
        solved_count INTEGER,
        PRIMARY KEY (username, date)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_problems (
        username TEXT,
        date TEXT,
        problem_title TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_numbers (
        title TEXT PRIMARY KEY,
        number TEXT
    )
    """)

    conn.commit()
    conn.close()


# ---------------- 题号缓存 ----------------

def get_question_number(title, title_slug=None):
    """先查本地缓存，没有再请求 API"""

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT number FROM question_numbers WHERE title = ?", (title,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0]

    # 没有缓存，去 Global API 查
    if not title_slug:
        title_slug = title.lower().replace(" ", "-").replace("(", "").replace(")", "").replace(",", "").replace("'", "")

    query = """
    query getQuestion($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionFrontendId
      }
    }
    """

    try:
        r = requests.post(
            LEETCODE_GLOBAL,
            json={"query": query, "variables": {"titleSlug": title_slug}},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=20
        )
        data = r.json()
        number = data["data"]["question"]["questionFrontendId"]

        # 存入缓存
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO question_numbers(title, number) VALUES (?, ?)", (title, number))
        conn.commit()
        conn.close()

        return number

    except Exception:
        return "?"


# ---------------- LeetCode API ----------------

def get_recent_ac_global(username):

    query = """
    query recentAcSubmissions($username: String!) {
      recentAcSubmissionList(username: $username) {
        id
        title
        titleSlug
        timestamp
      }
    }
    """

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://leetcode.com"
    }

    for _ in range(3):

        try:

            r = requests.post(
                LEETCODE_GLOBAL,
                json={"query": query, "variables": {"username": username}},
                headers=headers,
                timeout=20
            )

            data = r.json()

            if "data" not in data or data["data"] is None:
                return []

            return [
                {"title": s["title"], "titleSlug": s["titleSlug"], "timestamp": s["timestamp"]}
                for s in data["data"].get("recentAcSubmissionList", [])
            ]

        except requests.exceptions.RequestException:

            print("⚠️ retrying...")
            time.sleep(2)

    return []


def get_recent_ac_cn(username):

    query = """
    query {
      recentSubmissions(userSlug: "%s") {
        id
        status
        submitTime
        question {
          title
          questionFrontendId
        }
      }
    }
    """ % username

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://leetcode.cn"
    }

    for _ in range(3):

        try:

            r = requests.post(
                LEETCODE_CN,
                json={"query": query},
                headers=headers,
                timeout=20
            )

            data = r.json()

            if "data" not in data or data["data"] is None:
                return []

            results = []
            for s in data["data"].get("recentSubmissions", []):
                if s["status"] == "A_10":
                    title = s["question"]["title"]
                    number = s["question"]["questionFrontendId"]

                    # 直接缓存 CN 的题号
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR REPLACE INTO question_numbers(title, number) VALUES (?, ?)", (title, number))
                    conn.commit()
                    conn.close()

                    results.append({"title": title, "timestamp": s["submitTime"]})

            return results

        except requests.exceptions.RequestException:

            print("⚠️ retrying...")
            time.sleep(2)

    return []


def get_recent_ac(username):
    if username in CN_USERS:
        return get_recent_ac_cn(username)
    return get_recent_ac_global(username)


# ---------------- 统计当天 ----------------

def check_for_date(username, target_date):

    submissions = get_recent_ac(username)

    problems_dict = {}  # title -> titleSlug

    for sub in submissions:

        ts = datetime.fromtimestamp(
            int(sub["timestamp"]),
            timezone.utc
        ).astimezone(PACIFIC)

        if ts.date() == target_date:
            problems_dict[sub["title"]] = sub.get("titleSlug")

    # 查题号
    problems = []
    for title, title_slug in problems_dict.items():
        number = get_question_number(title, title_slug)
        time.sleep(0.5)  # 避免请求太快
        problems.append(f"{number}. {title}")

    problems.sort(key=lambda x: int(x.split(".")[0]) if x.split(".")[0].isdigit() else 9999)

    return len(problems), problems


# ---------------- DB 写入 ----------------

def save_record(username, date_str, count):

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO daily_records(username, date, solved_count)
        VALUES (?, ?, ?)
    """, (username, date_str, count))

    conn.commit()
    conn.close()


def save_problems(username, problems, date_str):

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM daily_problems
        WHERE username=? AND date=?
    """, (username, date_str))

    for title in problems:

        cursor.execute("""
            INSERT INTO daily_problems(username, date, problem_title)
            VALUES (?, ?, ?)
        """, (username, date_str, title))

    conn.commit()
    conn.close()


# ---------------- 主程序 ----------------

if __name__ == "__main__":

    init_db()

    if len(sys.argv) > 1:
        target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        target_date = datetime.now(PACIFIC).date()

    date_str = target_date.isoformat()

    print(f"\nChecking {date_str}\n")

    for user in USERS:

        try:

            count, problems = check_for_date(user, target_date)

            save_record(user, date_str, count)
            save_problems(user, problems, date_str)

            print(f"{user}: {count} solved -> {problems}")

            time.sleep(1)

        except Exception as e:

            print(f"⚠️ Error checking {user}: {e}")
