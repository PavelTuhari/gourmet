#!/usr/bin/env bash
# ┌─────────────────────────────────────────────────────────────┐
# │  planogram3d — НАТИВНОЕ приложение (двойной клик на macOS)  │
# │  Открывается системное окно программы, браузер не нужен.    │
# │  Первый запуск: ~1-2 минуты (установка окружения).          │
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
  echo "⏳ Первый запуск: готовлю окружение (~1-2 минуты)…"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip >/dev/null 2>&1 || true
echo "⏳ Проверяю зависимости…"
pip install -q plotly flask pywebview

echo ""
echo "🏪 Открываю нативное окно planogram3d…"
echo "   Внутри: карта сети → магазины → планограммы, зал, тренажёр,"
echo "   доставка, документация. Закрыть окно = выйти из программы."
echo ""
exec python -m planogram3d.desktop
