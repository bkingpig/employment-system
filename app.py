from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from io import BytesIO
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///employment.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')
    student_id = db.Column(db.String(50), unique=True, nullable=True)

class Employment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    major = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(20))
    employer = db.Column(db.String(200))
    status = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin123'), role='admin')
        db.session.add(admin)
    if not User.query.filter_by(username='zhangsan').first():
        user1 = User(username='zhangsan', password=generate_password_hash('123456'), role='user', student_id='20210001')
        db.session.add(user1)
    db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        records = Employment.query.all()
    else:
        records = Employment.query.filter_by(student_id=current_user.student_id).all()
    return render_template('dashboard.html', records=records)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_record():
    if request.method == 'POST':
        student_id = request.form['student_id']
        exist = Employment.query.filter_by(student_id=student_id).first()
        if exist:
            flash('学号已存在，请勿重复录入', 'error')
            return redirect(url_for('add_record'))
        name = request.form['name']
        employer = request.form['employer']
        if not student_id or not name or not employer:
            flash('学号、姓名、就业单位为必填项', 'error')
            return redirect(url_for('add_record'))
        new = Employment(
            student_id=student_id,
            name=name,
            major=request.form.get('major', ''),
            gender=request.form.get('gender', ''),
            phone=request.form.get('phone', ''),
            employer=employer,
            status=request.form.get('status', '')
        )
        db.session.add(new)
        db.session.commit()
        flash('添加成功', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_record(id):
    record = Employment.query.get_or_404(id)
    if current_user.role != 'admin' and record.student_id != current_user.student_id:
        flash('无权修改他人信息', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        record.name = request.form['name']
        record.major = request.form.get('major', '')
        record.gender = request.form.get('gender', '')
        record.phone = request.form.get('phone', '')
        record.employer = request.form['employer']
        record.status = request.form.get('status', '')
        db.session.commit()
        flash('修改成功', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit.html', record=record)

@app.route('/delete/<int:id>')
@login_required
def delete_record(id):
    record = Employment.query.get_or_404(id)
    if current_user.role != 'admin' and record.student_id != current_user.student_id:
        flash('无权删除他人信息', 'error')
        return redirect(url_for('dashboard'))
    db.session.delete(record)
    db.session.commit()
    flash('删除成功', 'success')
    return redirect(url_for('dashboard'))

@app.route('/search')
@login_required
def search():
    student_id = request.args.get('student_id', '')
    major = request.args.get('major', '')
    employer = request.args.get('employer', '')
    query = Employment.query
    if current_user.role != 'admin':
        query = query.filter_by(student_id=current_user.student_id)
    if student_id:
        query = query.filter(Employment.student_id.contains(student_id))
    if major:
        query = query.filter(Employment.major.contains(major))
    if employer:
        query = query.filter(Employment.employer.contains(employer))
    records = query.all()
    return render_template('dashboard.html', records=records)

@app.route('/import_excel', methods=['POST'])
@login_required
def import_excel():
    if current_user.role != 'admin':
        flash('仅管理员可批量导入', 'error')
        return redirect(url_for('dashboard'))
    file = request.files['file']
    if not file:
        flash('请选择文件', 'error')
        return redirect(url_for('dashboard'))
    try:
        df = pd.read_excel(file)
        success_count = 0
        fail_list = []
        for _, row in df.iterrows():
            student_id = str(row.get('学号', ''))
            name = str(row.get('姓名', ''))
            employer = str(row.get('就业单位', ''))
            if not student_id or not name or not employer:
                fail_list.append(f"学号{student_id}信息不完整")
                continue
            exist = Employment.query.filter_by(student_id=student_id).first()
            if exist:
                fail_list.append(f"学号{student_id}已存在")
                continue
            new = Employment(
                student_id=student_id,
                name=name,
                major=str(row.get('专业', '')),
                gender=str(row.get('性别', '')),
                phone=str(row.get('联系电话', '')),
                employer=employer,
                status=str(row.get('状态', ''))
            )
            db.session.add(new)
            success_count += 1
        db.session.commit()
        flash(f'导入成功 {success_count} 条，失败 {len(fail_list)} 条', 'success')
    except Exception as e:
        flash(f'导入失败：{str(e)}', 'error')
    return redirect(url_for('dashboard'))

@app.route('/export_excel')
@login_required
def export_excel():
    if current_user.role == 'admin':
        records = Employment.query.all()
    else:
        records = Employment.query.filter_by(student_id=current_user.student_id).all()
    data = [{
        '学号': r.student_id, '姓名': r.name, '专业': r.major,
        '性别': r.gender, '联系电话': r.phone, '就业单位': r.employer, '状态': r.status
    } for r in records]
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name='就业信息.xlsx', as_attachment=True)

@app.route('/export_pdf')
@login_required
def export_pdf():
    if current_user.role == 'admin':
        records = Employment.query.all()
    else:
        records = Employment.query.filter_by(student_id=current_user.student_id).all()
    html = '<html><head><meta charset="UTF-8"><title>就业信息</title></head><body><table border="1"><tr><th>学号</th><th>姓名</th><th>专业</th><th>就业单位</th></tr>'
    for r in records:
        html += f'<tr><td>{r.student_id}</td><td>{r.name}</td><td>{r.major}</td><td>{r.employer}</td></tr>'
    html += '</table></body></html>'
    return make_response(html)

if __name__ == '__main__':
    app.run(debug=True)