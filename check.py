import requests
import sqlite3
import sys
import time
from datetime import datetime, timezone
import pytz
from config import USERS

DB_FILE = "tracker.db"

PACIFIC = pytz.timezone("US/Pacific")

LEETCODE_GLOBAL = "https://leetcode.com/graphql"

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

    conn.commit()
    conn.close()


# ---------------- LeetCode API ----------------

def get_recent_ac(username):

    query = """
    query recentAcSubmissions($username: String!) {
      recentAcSubmissionList(username: $username) {
        id
        title
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
                json={
                    "query": query,
                    "variables": {"username": username}
                },
                headers=headers,
                timeout=20
            )

            data = r.json()

            if "data" not in data or data["data"] is None:
                return []

            return data["data"].get("recentAcSubmissionList", [])

        except requests.exceptions.RequestException:

            print("⚠️ retrying...")
            time.sleep(2)

    return []


# ---------------- 统计当天 ----------------

def check_for_date(username, target_date):

    submissions = get_recent_ac(username)

    problems_set = set()

    for sub in submissions:

        ts = datetime.fromtimestamp(
            int(sub["timestamp"]),
            timezone.utc
        ).astimezone(PACIFIC)

        if ts.date() == target_date:
            problems_set.add(sub["title"])

    problems = list(problems_set)
    count = len(problems)

    return count, problems


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

    # 先删当天记录避免重复
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

    # 支持补历史
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
