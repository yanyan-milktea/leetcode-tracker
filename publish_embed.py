import sqlite3
import requests
import sys
import subprocess
from datetime import datetime
from config import DISPLAY_NAME, WEBHOOK_URL

# ---------- 配置 ----------
DB_FILE = "tracker.db"
MENTION_ALL = False  # True 则自动 @everyone

# ---------- 日期 ----------
if len(sys.argv) > 1:
    target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
else:
    target_date = datetime.now().date()

date_str = target_date.isoformat()

# ---------- 先运行 check.py 更新数据库 ----------
subprocess.run(["python3", "check.py", date_str])

# ---------- 获取数据 ----------
def get_today_records():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # leaderboard: username -> solved_count
    cursor.execute(
        "SELECT username, solved_count FROM daily_records WHERE date = ? ORDER BY solved_count DESC", (date_str,)
    )
    leaderboard = cursor.fetchall()

    # today_problems: username -> [problems]
    cursor.execute(
        "SELECT username, problem_title FROM daily_problems WHERE date = ?", (date_str,)
    )
    rows = cursor.fetchall()
    today_problems = {}
    for username, problem in rows:
        today_problems.setdefault(username, []).append(problem)

    conn.close()
    return leaderboard, today_problems

# ---------- 计算 streak ----------
def get_streak(username):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT date, solved_count FROM daily_records WHERE username=? ORDER BY date DESC", (username,)
    )
    rows = cursor.fetchall()
    conn.close()

    streak = 0
    for date_db, solved_count in rows:
        if solved_count > 0:
            streak += 1
        else:
            break
    return max(streak, 1)  # 第一天天数就是1d

# ---------- 昨日排名 ----------
def get_yesterday_rank():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT username, solved_count
        FROM daily_records
        WHERE date = date(?, '-1 day')
        ORDER BY solved_count DESC
    """, (date_str,))

    rows = cursor.fetchall()
    conn.close()

    rank_map = {}
    prev = None
    rank = 0

    for i, (username, count) in enumerate(rows, 1):
        if count != prev:
            rank = i
        rank_map[username] = rank
        prev = count

    return rank_map


# ---------- streak leader ----------
def get_streak_leader():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT username FROM daily_records")
    users = cursor.fetchall()

    best_user = None
    best_streak = 0

    for (username,) in users:
        s = get_streak(username)
        if s > best_streak:
            best_streak = s
            best_user = username

    conn.close()
    return best_user, best_streak

# ---------- 构建 Discord Embed ----------
def build_embed():
    leaderboard, today_problems = get_today_records()

    yesterday_rank = get_yesterday_rank()
    streak_leader, best_streak = get_streak_leader()

    description = ""
    active_users = 0

    medals = ["👑", "🥈", "🥉"]

    # ---------- 重新构造 leaderboard ----------
    players = []

    for username, _ in leaderboard:
        problems = today_problems.get(username, [])
        problems = list(dict.fromkeys(problems))
        count = len(problems)
        players.append((username, count, problems))

    # 排序
    players.sort(key=lambda x: x[1], reverse=True)

    prev_count = None
    display_rank = 0

    for i, (username, count, problems) in enumerate(players, 1):

        if count != prev_count:
            display_rank = i

        prev_count = count

        display = DISPLAY_NAME.get(username, username)

        prob_str = "\n".join(f"📝 {p}" for p in problems) if problems else "—"

        if count > 0:
            active_users += 1

        medal = medals[display_rank - 1] if display_rank <= 3 else ""

        streak = get_streak(username)

        # ---------- rank change ----------
        change = ""
        if username in yesterday_rank:
            diff = yesterday_rank[username] - display_rank
            if diff > 0:
                change = f" ↑{diff}"
            elif diff < 0:
                change = f" ↓{abs(diff)}"

        description += (
            f"{display_rank}. {display}{medal}{change} — {count} solved | 🔥 {streak}d streak\n"
            f"{prob_str}\n\n"
        )

    # ---------- header ----------
    if active_users > 0:
        leader_name = DISPLAY_NAME.get(streak_leader, streak_leader)

        description = (
            f"👥 {active_users} people solved problems today\n"
            f"🔥 Longest streak: {leader_name} ({best_streak}d)\n\n"
            + description
        )
    else:
        description = "📊 No submissions today."

    embed = {
        "embeds": [{
            "title": f"🔥 Daily LeetCode Leaderboard ({date_str})",
            "description": description,
            "color": 16753920
        }]
    }

    if MENTION_ALL:
        embed["content"] = "@everyone"

    return embed

# ---------- 发送到 Discord ----------
def publish():
    embed = build_embed()
    resp = requests.post(WEBHOOK_URL, json=embed)
    if resp.status_code in [200, 204]:
        print(f"✅ Successfully published for {date_str}")
    else:
        print(f"⚠️ Failed: {resp.status_code} {resp.text}")

# ---------- 运行 ----------
if __name__ == "__main__":
    publish()
