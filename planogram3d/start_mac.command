#!/usr/bin/env bash
# ┌─────────────────────────────────────────────────────────────┐
# │  planogram3d — запуск двойным кликом на macOS               │
# │  Первый запуск: ~1 минута (создание окружения).             │
# │  Дальше: мгновенно. Остановить — Ctrl+C или закрыть окно.   │
# └─────────────────────────────────────────────────────────────┘
set -e
cd "$(dirname "$0")/.."            # корень репозитория gourmet

PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "❌ Не найден Python 3. Установите с https://www.python.org/downloads/"
  echo "Нажмите любую клавишу для выхода…"; read -n1 -s; exit 1
fi

VENV=".venv-planogram3d"
if [ ! -d "$VENV" ]; then
  echo "⏳ Первый запуск: готовлю окружение (~1 минута)…"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip >/dev/null 2>&1 || true
pip install -q plotly flask

URL="http://127.0.0.1:8050"
(
  sleep 2.5
  if command -v open >/dev/null 2>&1; then open "$URL"        # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"  # Linux
  fi
) &

echo ""
echo "🏪 planogram3d запускается — браузер откроется сам: $URL"
echo "   Карта сети → клик по магазину → планограмма/зал/тренажёр"
echo "   Остановить: Ctrl+C или закройте это окно."
echo ""
exec python -m planogram3d.webapp
