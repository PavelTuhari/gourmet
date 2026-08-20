#!/usr/bin/env bash
# ┌─────────────────────────────────────────────────────────────────┐
# │  Демонстрация автозаказа топлива (двойной клик на macOS)        │
# │  Сработает автозаказ на АЗС → откроется компактное окно поверх  │
# │  всех окон → бензовоз выедет к станции → показ сам перейдёт     │
# │  на 3D-планограмму заправки, где машина разгружается.           │
# └─────────────────────────────────────────────────────────────────┘
set -e
# запуск возможен двойным кликом из любого места: пакет planogram3d
# виден только из корня репозитория, а не изнутри самого пакета —
# именно на этом спотыкается ручной `python3 -m planogram3d...`
cd "$(dirname "$0")/.."

PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "❌ Не найден Python 3. Установите с https://www.python.org/downloads/"
  echo "Нажмите любую клавишу для выхода…"; read -n1 -s; exit 1
fi

VENV=".venv-planogram3d"
if [ ! -d "$VENV" ]; then
  echo "⏳ Первый запуск: готовлю окружение (~1-2 минуты)…"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip >/dev/null 2>&1 || true
echo "⏳ Проверяю зависимости…"
pip install -q plotly flask pywebview

echo ""
echo "⛽ Запускаю демонстрацию автозаказа…"
echo "   Окно откроется само, поверх остальных окон."
echo "   Закрыть окно = завершить демонстрацию."
echo ""
exec python -m planogram3d.webapp.tools.demo_autoorder "$@"
