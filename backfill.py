import requests
import sqlite3
import time
from datetime import datetime, timezone
import pytz
import json

DB_FILE = "tracker.db"
PACIFIC = pytz.timezone("US/Pacific")

from config import USERS, CN_USERS

LEETCODE_GLOBAL = "https://leetcode.com/graphql"
LEETCODE_CN = "https://leetcode.cn/graphql"

TARGET_DATES = ["2026-03-04", "2026-03-05", "2026-03-06"]

def get_calendar_global(username):
    query = """
    query userProfileCalendar($username: String!, $year: Int) {
      matchedUser(username: $username) {
        userCalendar(year: $year) {
          submissionCalendar
        }
      }
    }
    """
    try:
        r = requests.post(
            LEETCODE_GLOBAL,
            json={"query": query, "variables": {"username": username, "year": 2026}},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=20
        )
        data = r.json()
        calendar = json.loads(data["data"]["matchedUser"]["userCalendar"]["submissionCalendar"])

        result = {}
        for ts, count in calendar.items():
            # timestamp 是 UTC，转成太平洋时间日期
            pacific_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(PACIFIC).strftime("%Y-%m-%d")
            # calendar 的 count 是当天 UTC 的提交数，但日期要用太平洋时间
            # 累加（防止 UTC 日期跨越太平洋时区边界）
            if pacific_date in TARGET_DATES:
                result[pacific_date] = result.get(pacific_date, 0) + count
        return result
    except Exception as e:
        print(f"  error: {e}")
        return {}


def get_calendar_cn(username):
    query = """
    query {
      recentSubmissions(userSlug: "%s") {
        status
        submitTime
      }
    }
    """ % username
    try:
        r = requests.post(
            LEETCODE_CN,
            json={"query": query},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.cn"},
            timeout=20
        )
        data = r.json()
        result = {}
        for s in data["data"].get("recentSubmissions", []):
            if s["status"] == "A_10":
                pacific_date = datetime.fromtimestamp(int(s["submitTime"]), tz=timezone.utc).astimezone(PACIFIC).strftime("%Y-%m-%d")
                if pacific_date in TARGET_DATES:
                    result[pacific_date] = result.get(pacific_date, 0) + 1
        return result
    except Exception as e:
        print(f"  error: {e}")
        return {}


def insert_records(username, date_counts):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for date, count in date_counts.items():
        cursor.execute("""
            INSERT OR REPLACE INTO daily_records(username, date, solved_count)
            VALUES (?, ?, ?)
        """, (username, date, count))
        print(f"  inserted {date}: {count} solved")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    for user in USERS:
        print(f"\n{user}")
        if user in CN_USERS:
            counts = get_calendar_cn(user)
        else:
            counts = get_calendar_global(user)

        if counts:
            insert_records(user, counts)
        else:
            print("  no data found")

        time.sleep(1)

    print("\nDone")
