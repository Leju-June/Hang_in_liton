import sqlite3
import os
from flask import Flask, render_template, redirect, url_for, request, session, g, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, time

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ─── DB helpers ───────────────────────────────────────────────

def get_db():
    """Open a DB connection per request."""
    if 'db' not in session:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hangin.db')
        session['db'] = sqlite3.connect(db_path)
        session['db'].row_factory = sqlite3.Row
    return session['db']


def init_db():
    """Create tables if they don't exist."""
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            profile TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            trip_date TEXT,
            trip_place TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS match_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            meet_time DATETIME NOT NULL,
            meet_place TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_user_id) REFERENCES users(id),
            FOREIGN KEY (to_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            amount INTEGER NOT NULL,
            category TEXT,
            receipt_image TEXT,
            split_with TEXT DEFAULT '',
            date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF not EXISTS savings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            menu_photo TEXT,
            bot_comment TEXT,
            total_amount INTEGER,
            date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    db.commit()


# ─── Auth ─────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form['nickname']
        email = request.form['email']
        password = request.form['password']
        password_hash = generate_password_hash(password)
        db = get_db()
        try:
            db.execute('INSERT INTO users (nickname, email, password_hash) VALUES (?, ?, ?)',
                       (nickname, email, password_hash))
            db.commit()
            flash('회원가입이 완료되었습니다. 로그인해주세요.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('이미 가입된 이메일입니다.', 'danger')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['nickname'] = user['nickname']
            flash('로그인 되었습니다.', 'success')
            return redirect(url_for('home'))
        else:
            flash('이메일 또는 비밀번호가 잘못되었습니다.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃 되었습니다.', 'success')
    return redirect(url_for('home'))


# ─── Home (게시판) ───────────────────────────────────────────

@app.route('/')
def home():
    db = get_db()
    posts = db.execute('''
        SELECT posts.*, users.nickname
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.created_at DESC
    ''').fetchall()
    return render_template('home.html', posts=posts)


@app.route('/post/new', methods=['GET', 'POST'])
def post_new():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        body = request.form['body']
        trip_date = request.form.get('trip_date', '')
        trip_place = request.form.get('trip_place', '')
        db = get_db()
        db.execute(
            'INSERT INTO posts (user_id, title, body, trip_date, trip_place) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], title, body, trip_date, trip_place)
        )
        db.commit()
        flash('여행 모집 게시글이 등록되었습니다.', 'success')
        return redirect(url_for('home'))
    return render_template('post_new.html')


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    db = get_db()
    post = db.execute(
        'SELECT posts.*, users.nickname FROM posts JOIN users ON posts.user_id = users.id WHERE posts.id = ?',
        (post_id,)
    ).fetchone()
    return render_template('post_detail.html', post=post)


# ─── 매칭 (Match) ────────────────────────────────────────────

@app.route('/match')
def match_page():
    db = get_db()
    if 'user_id' in session:
        requests = db.execute(
            'SELECT * FROM match_requests WHERE to_user_id = ? OR from_user_id = ? ORDER BY created_at DESC',
            (session['user_id'], session['user_id'])
        ).fetchall()
    else:
        requests = []
    return render_template('match.html', requests=requests)


@app.route('/match/request', methods=['POST'])
def match_request():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    to_user_id = request.form['to_user_id']
    meet_time = request.form['meet_time']
    meet_place = request.form.get('meet_place', '')
    message = request.form.get('message', '')
    db = get_db()
    db.execute(
        'INSERT INTO match_requests (from_user_id, to_user_id, meet_time, meet_place, message) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], to_user_id, meet_time, meet_place, message)
    )
    db.commit()
    flash('매칭 요청이 전송되었습니다.', 'success')
    return redirect(url_for('match_page'))


@app.route('/match/accept/<int:request_id>')
def match_accept(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    db.execute('UPDATE match_requests SET status = ? WHERE id = ? AND to_user_id = ?',
               ('accepted', request_id, session['user_id']))
    db.commit()
    flash('매칭이 수락되었습니다!', 'success')
    return redirect(url_for('match_page'))


@app.route('/match/decline/<int:request_id>')
def match_decline(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    db.execute('UPDATE match_requests SET status = ? WHERE id = ? AND to_user_id = ?',
               ('declined', request_id, session['user_id']))
    db.commit()
    flash('매칭이 거절되었습니다.', 'info')
    return redirect(url_for('match_page'))


# ─── 정산 (Expense) ──────────────────────────────────────────

@app.route('/expense')
def expense_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    expenses = db.execute(
        'SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC',
        (session['user_id'],)
    ).fetchall()
    total = sum(e['amount'] for e in expenses)
    return render_template('expense.html', expenses=expenses, total=total)


@app.route('/expense/upload', methods=['POST'])
def expense_upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    title = request.form['title']
    amount = request.form.get('amount', 0, type=int)
    category = request.form.get('category', '기타')
    split_with = request.form.get('split_with', '')
    receipt = request.files.get('receipt_image')
    filename = ''
    if receipt and receipt.filename:
        filename = secure_filename(receipt.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        receipt.save(filepath)
    db = get_db()
    db.execute(
        'INSERT INTO expenses (user_id, title, amount, category, receipt_image, split_with) VALUES (?, ?, ?, ?, ?, ?)',
        (session['user_id'], title, amount, category, filename, split_with)
    )
    db.commit()
    flash('비용이 등록되었습니다.', 'success')
    return redirect(url_for('expense_page'))


# ─── 절약 (Saving) ──────────────────────────────────────────

@app.route('/saving')
def saving_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    savings = db.execute(
        'SELECT * FROM savings WHERE user_id = ? ORDER BY date DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template('saving.html', savings=savings)


@app.route('/saving/upload', methods=['POST'])
def saving_upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    menu_photo = request.files.get('menu_photo')
    filename = ''
    if menu_photo and menu_photo.filename:
        filename = secure_filename(menu_photo.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        menu_photo.save(filepath)
    bot_comment = request.form.get('bot_comment', '맛있는 메뉴네요! AI 분석은 곧 제공됩니다.')
    total_amount = request.form.get('total_amount', 0, type=int)
    db = get_db()
    db.execute(
        'INSERT INTO savings (user_id, menu_photo, bot_comment, total_amount) VALUES (?, ?, ?, ?)',
        (session['user_id'], filename, bot_comment, total_amount)
    )
    db.commit()
    flash('메뉴판이 등록되었습니다.', 'success')
    return redirect(url_for('saving_page'))


# ─── 마이페이지 (My Page) ───────────────────────────────────

@app.route('/my')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    return render_template('mypage.html', user=user)


@app.route('/my/profile', methods=['POST'])
def my_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    profile = request.form.get('profile', '')
    db = get_db()
    db.execute('UPDATE users SET profile = ? WHERE id = ?', (profile, session['user_id']))
    db.commit()
    flash('성향 정보가 업데이트되었습니다.', 'success')
    return redirect(url_for('mypage'))


@app.route('/my/password', methods=['POST'])
def my_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current = request.form['current_password']
    new = request.form['new_password']
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if check_password_hash(user['password_hash'], current):
        db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                   (generate_password_hash(new), session['user_id']))
        db.commit()
        flash('비밀번호가 변경되었습니다.', 'success')
    else:
        flash('현재 비밀번호가 올바르지 않습니다.', 'danger')
    return redirect(url_for('mypage'))


@app.route('/my/notifications', methods=['POST'])
def my_notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    push = request.form.get('push', 'off')
    email = request.form.get('email', 'off')
    db = get_db()
    db.execute('''
        UPDATE users SET
            push_notify = ?,
            email_notify = ?
        WHERE id = ?
    ''', (push, email, session['user_id']))
    db.commit()
    flash('알림 설정이 업데이트되었습니다.', 'success')
    return redirect(url_for('mypage'))


@app.route('/my/delete', methods=['POST'])
def my_delete():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (session['user_id'],))
    db.commit()
    session.clear()
    flash('회원탈퇴가 완료되었습니다. 감사합니다.', 'info')
    return redirect(url_for('home'))


# ─── Init DB on first run ────────────────────────────────────

with app.app_context():
    init_db()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
