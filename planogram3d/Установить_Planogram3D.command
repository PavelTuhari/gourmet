#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  УСТАНОВЩИК planogram3d для macOS — всё делает сам:          ║
# ║  скачивает проект → ставит окружение → создаёт ярлык на      ║
# ║  рабочем столе → запускает нативное окно программы.          ║
# ║  Достаточно открыть этот файл двойным кликом.                ║
# ╚══════════════════════════════════════════════════════════════╝
set -e

DEST="$HOME/PlanogramApp"
BRANCH="claude/3d-sales-visualization-fsbyam"
REPO="https://github.com/PavelTuhari/gourmet"

say() { echo ""; echo "▸ $1"; }

say "Установка planogram3d в $DEST"

# --- Python ---------------------------------------------------------
PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "❌ Не найден Python 3 (нужен 3.10+): https://www.python.org/downloads/"
  echo "Нажмите любую клавишу…"; read -n1 -s; exit 1
fi
say "Python: $($PY --version)"

# --- получение проекта (git, при его отсутствии — zip) --------------
mkdir -p "$DEST"
if [ -d "$DEST/gourmet/.git" ]; then
  say "Проект уже скачан — обновляю до свежей версии…"
  git -C "$DEST/gourmet" fetch origin "$BRANCH" -q
  git -C "$DEST/gourmet" checkout -q "$BRANCH"
  git -C "$DEST/gourmet" reset -q --hard "origin/$BRANCH"
elif command -v git >/dev/null 2>&1; then
  say "Скачиваю проект (git clone, ~15 МБ)…"
  git clone -q -b "$BRANCH" --depth 1 "$REPO.git" "$DEST/gourmet"
else
  say "git не найден — скачиваю архив…"
  curl -fsSL "$REPO/archive/refs/heads/$BRANCH.zip" -o "$DEST/src.zip"
  ditto -x -k "$DEST/src.zip" "$DEST/unzip" 2>/dev/null \
    || unzip -q -o "$DEST/src.zip" -d "$DEST/unzip"
  rm -rf "$DEST/gourmet"
  mv "$DEST/unzip/"gourmet-* "$DEST/gourmet"
  rm -rf "$DEST/src.zip" "$DEST/unzip"
fi

# --- окружение ------------------------------------------------------
VENV="$DEST/venv"
if [ ! -d "$VENV" ]; then
  say "Создаю окружение Python…"
  "$PY" -m venv "$VENV"
fi
say "Ставлю зависимости (plotly, flask, pywebview)…"
"$VENV/bin/pip" install -q --upgrade pip setuptools wheel
"$VENV/bin/pip" install -q plotly flask pywebview

# --- ярлык на рабочем столе -----------------------------------------
LAUNCHER="$HOME/Desktop/Planogram3D.command"
say "Создаю ярлык: $LAUNCHER"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
cd "$DEST/gourmet"
exec "$VENV/bin/python" -m planogram3d.desktop
EOF
chmod +x "$LAUNCHER"

# --- запуск ---------------------------------------------------------
say "Готово! Открываю нативное окно программы…"
echo "  В следующий раз: двойной клик по «Planogram3D.command» на рабочем столе."
cd "$DEST/gourmet"
exec "$VENV/bin/python" -m planogram3d.desktop
