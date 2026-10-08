import base64
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    """python-dotenv 없이 .env(KEY=VALUE)를 읽는다. 이미 설정된 환경변수가 우선한다."""
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(os.path.join(BASE_DIR, '.env'))

import clova  # noqa: E402
import travel_types as tt  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'hangin.db')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 국가: (국기, 이름, 통화, 현지 인사, 읽는 법)
COUNTRIES = {
    'FR': ('🇫🇷', '프랑스', 'EUR', 'Bonjour', '봉주르'),
    'IT': ('🇮🇹', '이탈리아', 'EUR', 'Ciao', '차오'),
    'ES': ('🇪🇸', '스페인', 'EUR', '¡Hola!', '올라'),
    'DE': ('🇩🇪', '독일', 'EUR', 'Hallo', '할로'),
    'GB': ('🇬🇧', '영국', 'GBP', 'Hello', '헬로'),
    'US': ('🇺🇸', '미국', 'USD', 'Hello', '헬로'),
    'JP': ('🇯🇵', '일본', 'JPY', 'こんにちは', '곤니치와'),
    'TW': ('🇹🇼', '대만', 'TWD', '你好', '니하오'),
    'TH': ('🇹🇭', '태국', 'THB', 'สวัสดี', '사와디캅'),
    'VN': ('🇻🇳', '베트남', 'VND', 'Xin chào', '신짜오'),
    'KR': ('🇰🇷', '한국', 'KRW', '안녕하세요', '안녕하세요'),
}
NO_DECIMAL_CURRENCIES = {'KRW', 'JPY', 'VND', 'TWD'}

POST_CATEGORIES = [('숙박', '🛏️'), ('이동', '🚕'), ('관광', '🗿'), ('문화', '🎨'), ('액티비티', '🏂'), ('식사', '🍜')]
CATEGORY_EMOJI = dict(POST_CATEGORIES)

AVATARS = ['avatar-yellow.png', 'avatar-lime.png', 'avatar-blue.png']


# ─── DB ──────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    profile TEXT DEFAULT '',
    travel_style TEXT DEFAULT '',
    budget TEXT DEFAULT '',
    personality TEXT DEFAULT '',
    push_notify TEXT DEFAULT 'on',
    email_notify TEXT DEFAULT 'off',
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
CREATE TABLE IF NOT EXISTS expense_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    settled INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS savings (
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
'''

# 기존 hangin.db를 지우지 않고 필요한 컬럼만 추가한다.
ADDED_COLUMNS = {
    'users': [
        ('country', "TEXT DEFAULT 'FR'"),
        ('contact', "TEXT DEFAULT ''"),
        ('gender', "TEXT DEFAULT ''"),
        ('birth_year', 'INTEGER'),
        ('travel_type', "TEXT DEFAULT ''"),
        ('travel_profile', "TEXT DEFAULT ''"),
        ('onboarding_answers', "TEXT DEFAULT ''"),
    ],
    'posts': [('category', "TEXT DEFAULT ''"), ('country', "TEXT DEFAULT ''")],
    'match_requests': [('post_id', 'INTEGER')],
    'expenses': [('payer', "TEXT DEFAULT ''"), ('currency', "TEXT DEFAULT ''")],
    'savings': [
        ('people', 'INTEGER DEFAULT 2'),
        ('currency', "TEXT DEFAULT ''"),
        ('note', "TEXT DEFAULT ''"),
        ('source', "TEXT DEFAULT ''"),
        ('ocr_text', "TEXT DEFAULT ''"),
        ('result_json', "TEXT DEFAULT ''"),
    ],
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    for table, columns in ADDED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        for name, decl in columns:
            if name not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')
    conn.commit()
    conn.close()


# ─── 공통 헬퍼 ───────────────────────────────────────────────

def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_urlsafe(32)
    return session['_csrf']


@app.before_request
def before_request():
    if request.method == 'POST':
        sent = request.form.get('_csrf') or request.headers.get('X-CSRF-Token', '')
        if not sent or not secrets.compare_digest(sent, session.get('_csrf', '')):
            abort(400, '요청이 만료되었어요. 새로고침 후 다시 시도해 주세요.')
    g.user = None
    if 'user_id' in session:
        g.user = get_db().execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash('로그인이 필요해요.', 'info')
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)
    return wrapped


def country_of(code):
    flag, name, currency, hello, hello_ko = COUNTRIES.get(code or 'FR', COUNTRIES['FR'])
    return {'code': code if code in COUNTRIES else 'FR', 'flag': flag, 'name': name, 'currency': currency,
            'hello': hello, 'hello_ko': hello_ko}


def load_json(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def travel_profile_of(user):
    return load_json(user['travel_profile']) if user and user['travel_profile'] else None


def avatar_of(user_id):
    return url_for('static', filename='img/' + AVATARS[(user_id or 0) % len(AVATARS)])


def money(value, currency=''):
    if value is None or value == '':
        return '-'
    value = float(value)
    if currency in NO_DECIMAL_CURRENCIES:
        text = f'{round(value):,}'
    else:
        text = f'{value:,.2f}'.rstrip('0').rstrip('.')
    return f'{currency} {text}'.strip()


def time_ago(value):
    if not value:
        return ''
    try:
        then = datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return str(value)[:16]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 1:
        return '방금 전'
    if minutes < 60:
        return f'{minutes}분 전'
    if minutes < 60 * 24:
        return f'{minutes // 60}시간 전'
    return f'{minutes // (60 * 24)}일 전'


app.jinja_env.filters['money'] = money
app.jinja_env.filters['time_ago'] = time_ago

TAB_BY_ENDPOINT = {
    'home': 'home',
    'match_page': 'match', 'match_new': 'match', 'match_posted': 'match', 'match_find': 'match',
    'post_detail': 'match', 'match_requests': 'match', 'match_request_detail': 'match',
    'expense_page': 'expense', 'saving_page': 'saving', 'saving_detail': 'saving',
    'mypage': 'my', 'travel_result': 'my',
}


@app.context_processor
def inject_globals():
    pending = 0
    if g.get('user'):
        pending = get_db().execute(
            "SELECT COUNT(*) FROM match_requests WHERE to_user_id = ? AND status = 'pending'",
            (g.user['id'],)).fetchone()[0]
    return {
        'csrf_token': csrf_token,
        'current_user': g.get('user'),
        'active_tab': TAB_BY_ENDPOINT.get(request.endpoint, ''),
        'pending_requests': pending,
        'avatar_of': avatar_of,
        'countries': COUNTRIES,
        'category_emoji': CATEGORY_EMOJI,
    }


IMAGE_SIGNATURES = [(b'\x89PNG', 'png'), (b'\xff\xd8\xff', 'jpg'), (b'RIFF', 'webp')]


def save_image(file_storage, prefix):
    """업로드 이미지를 확인 후 임의 이름으로 저장한다. (파일명, 바이트, 형식)을 돌려준다."""
    if not file_storage or not file_storage.filename:
        return None
    data = file_storage.read()
    if not data:
        return None
    fmt = next((f for sig, f in IMAGE_SIGNATURES if data.startswith(sig)), None)
    if fmt == 'webp' and data[8:12] != b'WEBP':
        fmt = None
    if fmt is None:
        raise ValueError('JPG, PNG, WEBP 이미지만 올릴 수 있어요.')
    filename = f'{prefix}_{uuid.uuid4().hex}.{fmt}'
    with open(os.path.join(UPLOAD_FOLDER, filename), 'wb') as f:
        f.write(data)
    return filename, data, fmt


@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.errorhandler(400)
def bad_request(err):
    flash(getattr(err, 'description', None) or '잘못된 요청이에요.', 'error')
    return redirect(request.referrer or url_for('home'))


@app.errorhandler(413)
def too_large(_err):
    flash('사진 용량이 너무 커요. 16MB 이하로 올려 주세요.', 'error')
    return redirect(request.referrer or url_for('home'))


# ─── 시작 화면 / 인증 ────────────────────────────────────────

def safe_next(target):
    return target if target and target.startswith('/') and not target.startswith('//') else None


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()[:20]
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not nickname or not email or len(password) < 8:
            flash('닉네임, 이메일, 8자 이상의 비밀번호를 입력해 주세요.', 'error')
            return render_template('register.html', form=request.form)
        if password != request.form.get('password_confirm', ''):
            flash('비밀번호가 서로 달라요.', 'error')
            return render_template('register.html', form=request.form)
        birth_year = request.form.get('birth_year', type=int)
        if birth_year and not (1900 <= birth_year <= datetime.now().year):
            birth_year = None
        db = get_db()
        try:
            cur = db.execute(
                '''INSERT INTO users (nickname, email, password_hash, gender, birth_year, contact, country)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (nickname, email, generate_password_hash(password),
                 request.form.get('gender', '')[:10], birth_year,
                 request.form.get('contact', '').strip()[:60], 'FR'))
            db.commit()
        except sqlite3.IntegrityError:
            flash('이미 가입된 이메일이에요.', 'error')
            return render_template('register.html', form=request.form)
        session.clear()
        session['user_id'] = cur.lastrowid
        session['nickname'] = nickname
        flash(f'{nickname}님, 반가워요! 여행 성향부터 알려주세요.', 'success')
        return redirect(url_for('onboarding'))
    return render_template('register.html', form={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = get_db().execute('SELECT * FROM users WHERE lower(email) = ?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], request.form.get('password', '')):
            session.clear()
            session['user_id'] = user['id']
            session['nickname'] = user['nickname']
            flash('로그인 되었어요.', 'success')
            if not user['travel_type']:
                return redirect(url_for('onboarding'))
            return redirect(safe_next(request.args.get('next')) or url_for('home'))
        flash('이메일 또는 비밀번호가 잘못되었어요.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃 되었어요.', 'success')
    return redirect(url_for('home'))


# ─── 온보딩: 여행 성향 3문항 → HyperCLOVA X 16유형 판단 ──────────

@app.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    if request.method == 'POST':
        answers = tt.clean_answers({key: request.form.getlist(key) for key in tt.QUESTION_KEYS})
        if not all(answers.values()):
            flash('세 가지 질문에 하나 이상씩 골라 주세요.', 'error')
            return redirect(url_for('onboarding'))
        try:
            profile = clova.analyze_travel_type(answers)
        except clova.ClovaError as e:
            app.logger.warning('travel type analysis failed: %s', e)
            profile = clova.fallback_travel_profile(answers)
            flash('AI 연결이 불안정해서 기본 분석 결과를 먼저 보여드려요. 마이페이지에서 다시 분석할 수 있어요.', 'info')
        db = get_db()
        db.execute('''UPDATE users SET travel_type = ?, travel_profile = ?, onboarding_answers = ?, travel_style = ?
                      WHERE id = ?''',
                   (profile['code'], json.dumps(profile, ensure_ascii=False),
                    json.dumps(answers, ensure_ascii=False), profile['name'], g.user['id']))
        db.commit()
        return redirect(url_for('travel_result'))
    answers = load_json(g.user['onboarding_answers'], {}) or {}
    return render_template('travel_tendencies.html', questions=tt.QUESTIONS, answers=answers)


@app.route('/onboarding/result')
@login_required
def travel_result():
    profile = travel_profile_of(g.user)
    if not profile:
        return redirect(url_for('onboarding'))
    return render_template('travel_result.html', profile=profile)


# ─── 홈 ──────────────────────────────────────────────────────

@app.route('/')
def home():
    if g.user is None:
        return render_template('splash.html')
    db = get_db()
    country = country_of(g.user['country'])
    posts = db.execute('''
        SELECT posts.*, users.nickname, users.travel_type FROM posts JOIN users ON posts.user_id = users.id
        WHERE posts.country = ? OR posts.country = '' OR posts.country IS NULL
        ORDER BY posts.created_at DESC LIMIT 3''', (country['code'],)).fetchall()
    return render_template('home.html', country=country, profile=travel_profile_of(g.user), posts=posts,
                           types=tt.TYPES)


@app.route('/country', methods=['POST'])
@login_required
def set_country():
    code = request.form.get('country', 'FR')
    if code in COUNTRIES:
        db = get_db()
        db.execute('UPDATE users SET country = ? WHERE id = ?', (code, g.user['id']))
        db.commit()
    return redirect(safe_next(request.form.get('next')) or url_for('home'))


# ─── 행인 매칭 ───────────────────────────────────────────────

@app.route('/match')
@login_required
def match_page():
    return render_template('match.html')


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def match_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()[:80]
        body = request.form.get('body', '').strip()[:3000]
        category = request.form.get('category', '')
        if not title or not body:
            flash('제목과 자세한 설명을 입력해 주세요.', 'error')
            return render_template('post_new.html', categories=POST_CATEGORIES, form=request.form)
        if category not in CATEGORY_EMOJI:
            category = ''
        db = get_db()
        cur = db.execute(
            '''INSERT INTO posts (user_id, title, body, trip_date, trip_place, category, country)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (g.user['id'], title, body, request.form.get('trip_date', '')[:10],
             request.form.get('trip_place', '').strip()[:80], category, country_of(g.user['country'])['code']))
        db.commit()
        return redirect(url_for('match_posted', post_id=cur.lastrowid))
    return render_template('post_new.html', categories=POST_CATEGORIES, form={})


@app.route('/post/<int:post_id>/done')
@login_required
def match_posted(post_id):
    return render_template('post_done.html', post_id=post_id)


@app.route('/match/find')
@login_required
def match_find():
    category = request.args.get('category', '')
    country = country_of(g.user['country'])
    sql = '''SELECT posts.*, users.nickname, users.travel_type,
                    (SELECT COUNT(*) FROM match_requests m WHERE m.post_id = posts.id) AS request_count
             FROM posts JOIN users ON posts.user_id = users.id
             WHERE (posts.country = ? OR posts.country = '' OR posts.country IS NULL)'''
    params = [country['code']]
    if category in CATEGORY_EMOJI:
        sql += ' AND posts.category = ?'
        params.append(category)
    sql += ' ORDER BY posts.created_at DESC'
    posts = get_db().execute(sql, params).fetchall()
    profile = travel_profile_of(g.user)
    best_code = (profile or {}).get('best_match', {}) or {}
    return render_template('match_post.html', posts=posts, categories=POST_CATEGORIES, category=category,
                           country=country, types=tt.TYPES, best_code=best_code.get('code'))


@app.route('/post/<int:post_id>')
@login_required
def post_detail(post_id):
    db = get_db()
    post = db.execute('''SELECT posts.*, users.nickname, users.travel_type, users.travel_profile
                         FROM posts JOIN users ON posts.user_id = users.id WHERE posts.id = ?''',
                      (post_id,)).fetchone()
    if post is None:
        abort(404)
    my_request = db.execute('SELECT * FROM match_requests WHERE post_id = ? AND from_user_id = ?',
                            (post_id, g.user['id'])).fetchone()
    received = []
    if post['user_id'] == g.user['id']:
        received = db.execute('''SELECT m.*, u.nickname, u.travel_type FROM match_requests m
                                 JOIN users u ON m.from_user_id = u.id
                                 WHERE m.post_id = ? ORDER BY m.created_at DESC''', (post_id,)).fetchall()
    return render_template('post_detail.html', post=post, author_profile=load_json(post['travel_profile']),
                           my_request=my_request, received=received, types=tt.TYPES)


@app.route('/post/<int:post_id>/request', methods=['POST'])
@login_required
def match_apply(post_id):
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if post is None:
        abort(404)
    if post['user_id'] == g.user['id']:
        flash('내 글에는 신청할 수 없어요.', 'error')
        return redirect(url_for('post_detail', post_id=post_id))
    exists = db.execute('SELECT 1 FROM match_requests WHERE post_id = ? AND from_user_id = ?',
                        (post_id, g.user['id'])).fetchone()
    if exists:
        flash('이미 행인 신청을 보냈어요.', 'info')
        return redirect(url_for('post_detail', post_id=post_id))
    db.execute('''INSERT INTO match_requests (from_user_id, to_user_id, meet_time, meet_place, message, post_id)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (g.user['id'], post['user_id'], request.form.get('meet_time', ''),
                request.form.get('meet_place', '').strip()[:80], request.form.get('message', '').strip()[:500],
                post_id))
    db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)',
               (post['user_id'], f"{g.user['nickname']}님이 '{post['title']}'에 행인 신청을 보냈어요."))
    db.commit()
    flash('행인 신청을 보냈어요! 상대가 수락하면 연락처가 공개돼요.', 'success')
    return redirect(url_for('post_detail', post_id=post_id))


@app.route('/match/requests')
@login_required
def match_requests():
    db = get_db()
    received = db.execute('''SELECT m.*, u.nickname, u.travel_type, p.title AS post_title FROM match_requests m
                             JOIN users u ON m.from_user_id = u.id LEFT JOIN posts p ON m.post_id = p.id
                             WHERE m.to_user_id = ? ORDER BY m.created_at DESC''', (g.user['id'],)).fetchall()
    sent = db.execute('''SELECT m.*, u.nickname, u.travel_type, p.title AS post_title FROM match_requests m
                         JOIN users u ON m.to_user_id = u.id LEFT JOIN posts p ON m.post_id = p.id
                         WHERE m.from_user_id = ? ORDER BY m.created_at DESC''', (g.user['id'],)).fetchall()
    return render_template('match_requests.html', received=received, sent=sent, types=tt.TYPES,
                           tab=request.args.get('tab', 'received'))


def load_request_for_user(request_id):
    req = get_db().execute('SELECT * FROM match_requests WHERE id = ?', (request_id,)).fetchone()
    if req is None or g.user['id'] not in (req['from_user_id'], req['to_user_id']):
        abort(404)
    return req


@app.route('/match/request/<int:request_id>')
@login_required
def match_request_detail(request_id):
    req = load_request_for_user(request_id)
    db = get_db()
    is_receiver = req['to_user_id'] == g.user['id']
    other_id = req['from_user_id'] if is_receiver else req['to_user_id']
    other = db.execute('SELECT * FROM users WHERE id = ?', (other_id,)).fetchone()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (req['post_id'],)).fetchone() if req['post_id'] else None
    return render_template('match_request.html', req=req, other=other, post=post, is_receiver=is_receiver,
                           other_profile=travel_profile_of(other),
                           other_answers=load_json(other['onboarding_answers'], {}) or {},
                           other_country=country_of(other['country']), questions=tt.QUESTIONS)


def respond_request(request_id, status):
    req = load_request_for_user(request_id)
    if req['to_user_id'] != g.user['id'] or req['status'] != 'pending':
        abort(400, '이 요청에는 응답할 수 없어요.')
    db = get_db()
    db.execute('UPDATE match_requests SET status = ? WHERE id = ?', (status, request_id))
    text = '수락했어요! 이제 연락처를 확인할 수 있어요.' if status == 'accepted' else '정중하게 거절했어요.'
    db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)',
               (req['from_user_id'], f"{g.user['nickname']}님이 행인 신청을 {text}"))
    db.commit()
    return redirect(url_for('match_request_detail', request_id=request_id))


@app.route('/match/request/<int:request_id>/accept', methods=['POST'])
@login_required
def match_accept(request_id):
    flash('행인 매칭이 성사됐어요! 🎉', 'success')
    return respond_request(request_id, 'accepted')


@app.route('/match/request/<int:request_id>/decline', methods=['POST'])
@login_required
def match_decline(request_id):
    flash('매칭 요청을 거절했어요.', 'info')
    return respond_request(request_id, 'declined')


# ─── 정산 ────────────────────────────────────────────────────

def expense_members(user):
    db = get_db()
    members = db.execute('SELECT * FROM expense_members WHERE user_id = ? ORDER BY id', (user['id'],)).fetchall()
    if not members:
        db.execute('INSERT INTO expense_members (user_id, name) VALUES (?, ?)', (user['id'], user['nickname']))
        db.commit()
        members = db.execute('SELECT * FROM expense_members WHERE user_id = ? ORDER BY id', (user['id'],)).fetchall()
    return members


def split_names(text):
    return [n.strip() for n in (text or '').split(',') if n.strip()]


def settle(members, expenses):
    names = [m['name'] for m in members]
    balance = {n: 0.0 for n in names}
    for e in expenses:
        people = [n for n in split_names(e['split_with']) if n in balance] or names
        share = float(e['amount']) / len(people)
        if e['payer'] in balance:
            balance[e['payer']] += float(e['amount'])
        for n in people:
            balance[n] -= share
    creditors = sorted(((n, v) for n, v in balance.items() if v > 0.005), key=lambda x: -x[1])
    debtors = sorted(((n, -v) for n, v in balance.items() if v < -0.005), key=lambda x: -x[1])
    transfers, ci, di = [], 0, 0
    creditors = [list(c) for c in creditors]
    debtors = [list(d) for d in debtors]
    while ci < len(creditors) and di < len(debtors):
        amount = min(creditors[ci][1], debtors[di][1])
        transfers.append({'from': debtors[di][0], 'to': creditors[ci][0], 'amount': round(amount, 2)})
        creditors[ci][1] -= amount
        debtors[di][1] -= amount
        if creditors[ci][1] < 0.005:
            ci += 1
        if debtors[di][1] < 0.005:
            di += 1
    return balance, transfers


@app.route('/expense')
@login_required
def expense_page():
    db = get_db()
    members = expense_members(g.user)
    expenses = db.execute('SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC',
                          (g.user['id'],)).fetchall()
    currency = country_of(g.user['country'])['currency']
    balance, transfers = settle(members, expenses)
    total = sum(float(e['amount']) for e in expenses)
    paid = {m['name']: 0.0 for m in members}
    for e in expenses:
        if e['payer'] in paid:
            paid[e['payer']] += float(e['amount'])
    prefill = {'title': request.args.get('title', ''), 'amount': request.args.get('amount', '')}
    return render_template('expense.html', members=members, expenses=expenses, total=total, balance=balance,
                           transfers=transfers, currency=currency, paid=paid, prefill=prefill,
                           settled_count=sum(1 for m in members if m['settled']))


@app.route('/expense/add', methods=['POST'])
@login_required
def expense_add():
    db = get_db()
    names = [m['name'] for m in expense_members(g.user)]
    title = request.form.get('title', '').strip()[:60]
    try:
        amount = round(float(request.form.get('amount', '').replace(',', '')), 2)
    except ValueError:
        amount = 0
    if not title or amount <= 0:
        flash('제목과 0보다 큰 금액을 입력해 주세요.', 'error')
        return redirect(url_for('expense_page'))
    payer = request.form.get('payer') if request.form.get('payer') in names else names[0]
    participants = [n for n in request.form.getlist('participants') if n in names] or names
    try:
        saved = save_image(request.files.get('receipt_image'), 'receipt')
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('expense_page'))
    db.execute('''INSERT INTO expenses (user_id, title, amount, category, receipt_image, split_with, payer, currency)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
               (g.user['id'], title, amount, request.form.get('category', '기타')[:10], saved[0] if saved else '',
                ','.join(participants), payer, country_of(g.user['country'])['currency']))
    db.execute('UPDATE expense_members SET settled = 0 WHERE user_id = ?', (g.user['id'],))
    db.commit()
    flash('지출을 기록했어요.', 'success')
    return redirect(url_for('expense_page'))


@app.route('/expense/<int:expense_id>/delete', methods=['POST'])
@login_required
def expense_delete(expense_id):
    db = get_db()
    db.execute('DELETE FROM expenses WHERE id = ? AND user_id = ?', (expense_id, g.user['id']))
    db.commit()
    flash('지출 기록을 삭제했어요.', 'info')
    return redirect(url_for('expense_page'))


@app.route('/expense/members/add', methods=['POST'])
@login_required
def expense_member_add():
    db = get_db()
    members = expense_members(g.user)
    name = request.form.get('name', '').strip().replace(',', ' ')[:20]
    if not name:
        taken = {m['name'] for m in members}
        name = next(f'행인 {i}' for i in range(len(members) + 1, 100) if f'행인 {i}' not in taken)
    try:
        db.execute('INSERT INTO expense_members (user_id, name) VALUES (?, ?)', (g.user['id'], name))
        db.commit()
    except sqlite3.IntegrityError:
        flash('이미 있는 이름이에요.', 'error')
    return redirect(url_for('expense_page'))


@app.route('/expense/members/remove', methods=['POST'])
@login_required
def expense_member_remove():
    db = get_db()
    members = expense_members(g.user)
    expenses = db.execute('SELECT payer, split_with FROM expenses WHERE user_id = ?', (g.user['id'],)).fetchall()
    used = {e['payer'] for e in expenses} | {n for e in expenses for n in split_names(e['split_with'])}
    removable = [m for m in members[1:] if m['name'] not in used]
    if not removable:
        flash('지출 기록에 포함된 멤버는 뺄 수 없어요.', 'error')
    else:
        db.execute('DELETE FROM expense_members WHERE id = ?', (removable[-1]['id'],))
        db.commit()
    return redirect(url_for('expense_page'))


@app.route('/expense/members/<int:member_id>/toggle', methods=['POST'])
@login_required
def expense_member_toggle(member_id):
    db = get_db()
    db.execute('UPDATE expense_members SET settled = 1 - settled WHERE id = ? AND user_id = ?',
               (member_id, g.user['id']))
    db.commit()
    return redirect(url_for('expense_page'))


# ─── 절약: 외국 메뉴판 → OCR → HyperCLOVA X 절약형 N빵 가이드 ──────────

@app.route('/saving')
@login_required
def saving_page():
    savings = get_db().execute('SELECT * FROM savings WHERE user_id = ? ORDER BY date DESC, id DESC',
                               (g.user['id'],)).fetchall()
    history = [{'row': s, 'guide': load_json(s['result_json'], {}) or {}} for s in savings]
    members = len(expense_members(g.user))
    return render_template('saving.html', history=history, default_people=max(2, members),
                           country=country_of(g.user['country']))


@app.route('/saving/analyze', methods=['POST'])
@login_required
def saving_analyze():
    people = max(1, min(request.form.get('people', 2, type=int) or 2, 12))
    note = request.form.get('note', '').strip()[:200]
    try:
        saved = save_image(request.files.get('menu_photo'), 'menu')
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('saving_page'))
    if not saved:
        flash('메뉴판 사진을 올려 주세요.', 'error')
        return redirect(url_for('saving_page'))
    filename, data, fmt = saved
    country = country_of(g.user['country'])

    ocr_result, source = '', 'vision'
    if clova.ocr_configured() and fmt in ('jpg', 'png'):
        try:
            ocr_result = clova.ocr_text(data, fmt)
            source = 'ocr'
        except clova.ClovaError as e:
            app.logger.warning('OCR failed, falling back to HCX vision: %s', e)
    if len(ocr_result.strip()) < 8:
        ocr_result, source = '', 'vision'
    try:
        guide = clova.analyze_menu(people=people, country_name=country['name'], currency=country['currency'],
                                   note=note, travel_type=travel_profile_of(g.user), ocr=ocr_result or None,
                                   image_b64=None if ocr_result else base64.b64encode(data).decode())
    except clova.ClovaError as e:
        app.logger.warning('menu guide failed: %s', e)
        flash(f'행이가 메뉴판을 분석하지 못했어요. {e}', 'error')
        os.remove(os.path.join(UPLOAD_FOLDER, filename))
        return redirect(url_for('saving_page'))
    db = get_db()
    cur = db.execute('''INSERT INTO savings (user_id, menu_photo, bot_comment, total_amount, people, currency, note,
                                             source, ocr_text, result_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (g.user['id'], filename, guide['summary'], guide['total'], people, guide['currency'], note,
                      source, ocr_result, json.dumps(guide, ensure_ascii=False)))
    db.commit()
    return redirect(url_for('saving_detail', saving_id=cur.lastrowid))


@app.route('/saving/<int:saving_id>')
@login_required
def saving_detail(saving_id):
    row = get_db().execute('SELECT * FROM savings WHERE id = ? AND user_id = ?',
                           (saving_id, g.user['id'])).fetchone()
    if row is None:
        abort(404)
    return render_template('saving_result.html', row=row, guide=load_json(row['result_json'], {}) or {})


@app.route('/saving/<int:saving_id>/delete', methods=['POST'])
@login_required
def saving_delete(saving_id):
    db = get_db()
    row = db.execute('SELECT * FROM savings WHERE id = ? AND user_id = ?', (saving_id, g.user['id'])).fetchone()
    if row:
        db.execute('DELETE FROM savings WHERE id = ?', (saving_id,))
        db.commit()
        if row['menu_photo']:
            path = os.path.join(UPLOAD_FOLDER, os.path.basename(row['menu_photo']))
            if os.path.exists(path):
                os.remove(path)
        flash('분석 기록을 삭제했어요.', 'info')
    return redirect(url_for('saving_page'))


# ─── 마이페이지 ──────────────────────────────────────────────

@app.route('/my')
@login_required
def mypage():
    db = get_db()
    uid = g.user['id']
    stats = {
        'posts': db.execute('SELECT COUNT(*) FROM posts WHERE user_id = ?', (uid,)).fetchone()[0],
        'matches': db.execute('''SELECT COUNT(*) FROM match_requests WHERE status = 'accepted'
                                 AND (from_user_id = ? OR to_user_id = ?)''', (uid, uid)).fetchone()[0],
        'savings': db.execute('SELECT COUNT(*) FROM savings WHERE user_id = ?', (uid,)).fetchone()[0],
    }
    notifications = db.execute('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
                               (uid,)).fetchall()
    return render_template('mypage.html', profile=travel_profile_of(g.user), stats=stats,
                           answers=load_json(g.user['onboarding_answers'], {}) or {}, questions=tt.QUESTIONS,
                           country=country_of(g.user['country']), notifications=notifications)


@app.route('/profile/edit', methods=['POST'])
@login_required
def profile_edit():
    nickname = request.form.get('nickname', '').strip()[:20]
    if not nickname:
        flash('닉네임을 입력해 주세요.', 'error')
        return redirect(url_for('mypage'))
    birth_year = request.form.get('birth_year', type=int)
    if birth_year and not (1900 <= birth_year <= datetime.now().year):
        birth_year = None
    db = get_db()
    db.execute('''UPDATE users SET nickname = ?, profile = ?, contact = ?, gender = ?, birth_year = ?
                  WHERE id = ?''',
               (nickname, request.form.get('profile', '').strip()[:200], request.form.get('contact', '').strip()[:60],
                request.form.get('gender', '')[:10], birth_year, g.user['id']))
    db.commit()
    session['nickname'] = nickname
    flash('프로필을 수정했어요.', 'success')
    return redirect(url_for('mypage'))


@app.route('/password/change', methods=['POST'])
@login_required
def password_change():
    new = request.form.get('new_password', '')
    if not check_password_hash(g.user['password_hash'], request.form.get('current_password', '')):
        flash('현재 비밀번호가 올바르지 않아요.', 'error')
    elif len(new) < 8:
        flash('새 비밀번호는 8자 이상이어야 해요.', 'error')
    else:
        db = get_db()
        db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(new), g.user['id']))
        db.commit()
        flash('비밀번호를 변경했어요.', 'success')
    return redirect(url_for('mypage'))


@app.route('/my/notifications', methods=['POST'])
@login_required
def my_notifications():
    db = get_db()
    db.execute('UPDATE users SET push_notify = ?, email_notify = ? WHERE id = ?',
               ('on' if request.form.get('push') else 'off', 'on' if request.form.get('email') else 'off',
                g.user['id']))
    db.commit()
    flash('알림 설정을 저장했어요.', 'success')
    return redirect(url_for('mypage'))


@app.route('/profile/delete', methods=['POST'])
@login_required
def profile_delete():
    db = get_db()
    uid = g.user['id']
    for table, column in [('notifications', 'user_id'), ('savings', 'user_id'), ('expenses', 'user_id'),
                          ('expense_members', 'user_id'), ('match_requests', 'from_user_id'),
                          ('match_requests', 'to_user_id')]:
        db.execute(f'DELETE FROM {table} WHERE {column} = ?', (uid,))
    db.execute('DELETE FROM match_requests WHERE post_id IN (SELECT id FROM posts WHERE user_id = ?)', (uid,))
    db.execute('DELETE FROM posts WHERE user_id = ?', (uid,))
    db.execute('DELETE FROM users WHERE id = ?', (uid,))
    db.commit()
    session.clear()
    flash('회원탈퇴가 완료되었어요. 그동안 감사했어요.', 'info')
    return redirect(url_for('home'))


with app.app_context():
    init_db()


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1', host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
