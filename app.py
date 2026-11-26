from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime, timezone

app = Flask(__name__)
DB_PATH = 'tasks.db'
MAX_PER_PAGE = 100


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        priority INTEGER DEFAULT 1,
        completed INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if count == 0:
        now = datetime.now(timezone.utc).isoformat()
        c.executemany(
            "INSERT INTO tasks (title, description, priority, completed, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("Купить молоко", "2 литра", 1, 0, now),
                ("Позвонить маме", "", 2, 0, now),
                ("Сдать отчёт", "до пятницы", 3, 1, now),
            ],
        )
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    status = request.args.get('status', 'all')
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(max(1, int(request.args.get('per_page', 10))), MAX_PER_PAGE)
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400

    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM tasks"
    params = []
    
    # FIX 1a и 1b: правильные фильтры
    if status == 'active':
        query += " WHERE completed = 0"
    elif status == 'completed':
        query += " WHERE completed = 1"

    offset = (page - 1) * per_page
    # FIX 2: правильный LIMIT и параметризация
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    rows = c.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tasks/search', methods=['GET'])
def search_tasks():
    q = request.args.get('q', '')
    # FIX 3: защита от SQL-инъекций через параметризацию и экранирование
    escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    conn = get_db()
    c = conn.cursor()
    rows = c.execute(
        "SELECT * FROM tasks WHERE title LIKE ? ESCAPE '\\'",
        (f"%{escaped}%",),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json() or {}
    
    # FIX 4: валидация title
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
        
    description = data.get('description', '') or ''
    try:
        priority = int(data.get('priority', 1))
    except (TypeError, ValueError):
        return jsonify({"error": "priority must be an integer"}), 400

    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (title, description, priority, created_at) "
        "VALUES (?, ?, ?, ?)",
        (title, description, priority, created_at),
    )
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    # FIX 5: возвращаем 201 Created
    return jsonify({"id": task_id, "message": "created"}), 201


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json() or {}
    conn = get_db()
    c = conn.cursor()
    updated = False
    
    # FIX 6: добавлен WHERE id = ?
    if 'completed' in data:
        c.execute("UPDATE tasks SET completed = ? WHERE id = ?",
                  (1 if data['completed'] else 0, task_id))
        updated = updated or c.rowcount > 0
        
    if 'title' in data:
        new_title = (data['title'] or '').strip()
        if not new_title:
            conn.close()
            return jsonify({"error": "title cannot be empty"}), 400
        c.execute("UPDATE tasks SET title = ? WHERE id = ?", (new_title, task_id))
        updated = updated or c.rowcount > 0
        
    conn.commit()
    conn.close()
    if not updated:
        return jsonify({"error": "not found or nothing to update"}), 404
    return jsonify({"message": "updated"})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = get_db()
    c = conn.cursor()
    # FIX 7: реальное удаление из БД
    c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"message": "deleted"})


@app.route('/api/stats', methods=['GET'])
def stats():
    conn = get_db()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    completed = c.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1").fetchone()[0]
    conn.close()
    # FIX 8: возвращаем проценты, а не долю
    rate = round(completed / total * 100, 2) if total > 0 else 0
    return jsonify({
        "total": total,
        "completed": completed,
        "active": total - completed,
        "rate": rate,
    })


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
