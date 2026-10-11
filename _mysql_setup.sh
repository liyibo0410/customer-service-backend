#!/usr/bin/env bash
# 临时脚本：为本项目初始化一个专用 MySQL 实例并验证连通
set -u

BASEDIR="D:/software/Program Files/MySQL/MySQL Server 8.0"
DATADIR="D:/mysql-data-cs"
MYSQLD="$BASEDIR/bin/mysqld.exe"
MYSQL="$BASEDIR/bin/mysql.exe"
ROOT="D:/software/PycharmProjects/customer-service-backend"
LOG="$ROOT/_mysql_setup.txt"

: > "$LOG"
say() { echo "$@" >> "$LOG"; }

say "===== MySQL 专用实例初始化 ====="
say "basedir = $BASEDIR"
say "datadir = $DATADIR"
say "time    = $(date '+%Y-%m-%d %H:%M:%S')"
say ""

if [ -d "$DATADIR/mysql" ]; then
  say "[跳过] 数据目录已初始化过"
else
  say "--- [1] 初始化数据目录（root 无密码）---"
  mkdir -p "$DATADIR"
  "$MYSQLD" --initialize-insecure --basedir="$BASEDIR" --datadir="$DATADIR" --console > "$ROOT/_mysql_init.log" 2>&1
  if [ -d "$DATADIR/mysql" ]; then
    say "初始化成功"
  else
    say "初始化失败，日志尾部："
    tail -25 "$ROOT/_mysql_init.log" >> "$LOG"
    cat "$LOG"
    exit 1
  fi
fi
say ""

say "--- [2] 先确认 3306 空闲 ---"
if netstat -ano 2>/dev/null | grep -q "127.0.0.1:3306 .*LISTENING\|0.0.0.0:3306 .*LISTENING"; then
  say "3306 已被占用，脚本中止（不覆盖别人的实例）"
  netstat -ano 2>/dev/null | grep ":3306 " | head -3 >> "$LOG"
  cat "$LOG"
  exit 1
fi
say "3306 空闲"
say ""

say "--- [3] 启动 mysqld ---"
"$MYSQLD" --basedir="$BASEDIR" --datadir="$DATADIR" --port=3306 --console > "$ROOT/_mysql_run.log" 2>&1 &
MPID=$!
sleep 15
if netstat -ano 2>/dev/null | grep -q ":3306 .*LISTENING"; then
  say "mysqld 已监听 3306 (pid=$MPID)"
else
  say "mysqld 未监听，日志尾部："
  tail -25 "$ROOT/_mysql_run.log" >> "$LOG"
fi
say ""

say "--- [4] 设置 root 密码为 .env 里的值 ---"
"$MYSQL" -u root --port=3306 --protocol=tcp --skip-password \
  -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'itwwy123@'; FLUSH PRIVILEGES;" >> "$LOG" 2>&1 \
  && say "密码设置成功" || say "密码设置失败（可能已经设过）"
say ""

say "--- [5] 用 .env 里的凭据连一次 ---"
"$MYSQL" -u root -p'itwwy123@' --port=3306 --protocol=tcp \
  -e "SELECT VERSION() AS version, CURRENT_USER() AS who;" >> "$LOG" 2>&1 \
  && say "凭据可用" || say "凭据不可用"
say ""

say "--- [6] 建库 ---"
"$MYSQL" -u root -p'itwwy123@' --port=3306 --protocol=tcp \
  -e "CREATE DATABASE IF NOT EXISTS customer_service DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; SHOW DATABASES;" >> "$LOG" 2>&1
say ""

say "===== 完成 ====="
cat "$LOG"
