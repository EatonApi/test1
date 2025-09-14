from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///competition.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 数据库模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    team_name = db.Column(db.String(100), nullable=True)  # 新增队伍名称
    province = db.Column(db.String(50), nullable=True)    # 新增省份
    is_admin = db.Column(db.Boolean, default=False)
    registrations = db.relationship('Registration', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Competition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    form_fields = db.Column(db.Text, nullable=False)  # JSON格式的表单字段
    registrations = db.relationship('Registration', backref='competition', lazy=True)
    
    def __repr__(self):
        return f'<Competition {self.title}>'

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    form_data = db.Column(db.Text, nullable=False)  # JSON格式的表单数据
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # 新增状态字段: pending/confirmed/rejected
    
    def __repr__(self):
        return f'<Registration {self.id}>'

class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    publish_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_public = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # 针对特定用户的通知
    
    def __repr__(self):
        return f'<Notice {self.title}>'

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 针对特定用户的安排
    
    def __repr__(self):
        return f'<Schedule {self.title}>'

# 创建数据库
with app.app_context():
    db.create_all()
    
    # 创建初始管理员用户
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin', 
            password='admin123', 
            is_admin=True, 
            name='管理员', 
            email='admin@example.com', 
            phone='1234567890',
            team_name='管理员团队',
            province='北京'
        )
        db.session.add(admin)
        db.session.commit()

# 辅助函数
def is_logged_in():
    return 'user_id' in session

def is_admin():
    return 'is_admin' in session and session['is_admin']

def get_current_user():
    if is_logged_in():
        return User.query.get(session['user_id'])
    return None

# 添加自定义模板过滤器
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value)
    except:
        return {}
    
@app.template_filter('to_pretty_json')
def to_pretty_json_filter(value):
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except:
        return value

# 路由
@app.route('/')
def home():
    competitions = Competition.query.order_by(Competition.start_date.desc()).all()
    public_notices = Notice.query.filter_by(is_public=True).order_by(Notice.publish_date.desc()).limit(5).all()
    return render_template('index.html', competitions=competitions, public_notices=public_notices)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('登录成功！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('用户名或密码错误', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('您已成功登出', 'success')
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        flash('请先登录', 'warning')
        return redirect(url_for('login'))
    
    user = get_current_user()
    user_schedules = Schedule.query.filter_by(user_id=user.id).order_by(Schedule.start_time).all()
    user_notices = Notice.query.filter((Notice.user_id == user.id) | (Notice.is_public == True)).order_by(Notice.publish_date.desc()).limit(10).all()
    user_registrations = Registration.query.filter_by(user_id=user.id).all()
    
    # 获取比赛信息
    competitions = {}
    for reg in user_registrations:
        competitions[reg.competition_id] = Competition.query.get(reg.competition_id)
    
    return render_template('dashboard.html', 
                          user=user,
                          schedules=user_schedules,
                          notices=user_notices,
                          registrations=user_registrations,
                          competitions=competitions)

@app.route('/competition/<int:id>', methods=['GET', 'POST'])
def competition_detail(id):
    competition = Competition.query.get_or_404(id)
    public_notices = Notice.query.filter_by(is_public=True).order_by(Notice.publish_date.desc()).limit(3).all()
    
    if request.method == 'POST':
        # 处理报名表单
        form_data = {}
        fields = json.loads(competition.form_fields)
        
        for field in fields:
            field_name = field['name']
            field_value = request.form.get(field_name, '')
            form_data[field_name] = field_value
        
        # 创建报名记录
        registration = Registration(
            competition_id=competition.id,
            form_data=json.dumps(form_data, ensure_ascii=False),
            status='pending'  # 默认状态为待确认
        )
        
        # 如果用户已登录，关联用户
        if is_logged_in():
            registration.user_id = session['user_id']
        
        db.session.add(registration)
        db.session.commit()
        
        flash('报名成功！管理员将在审核后确认您的报名', 'success')
        return redirect(url_for('competition_detail', id=id))
    
    return render_template('competition_detail.html', 
                          competition=competition,
                          form_fields=json.loads(competition.form_fields),
                          public_notices=public_notices)

@app.route('/notice/<int:id>')
def notice_detail(id):
    notice = Notice.query.get_or_404(id)
    
    # 检查用户是否有权查看此通知
    if not notice.is_public and (not is_logged_in() or notice.user_id != session['user_id']):
        flash('您无权查看此通知', 'danger')
        return redirect(url_for('home'))
    
    return render_template('notice_detail.html', notice=notice)

@app.route('/registration/<int:id>')
def registration_detail(id):
    if not is_logged_in():
        flash('请先登录', 'warning')
        return redirect(url_for('login'))
    
    registration = Registration.query.get_or_404(id)
    
    # 检查用户是否有权查看此报名
    if registration.user_id != session['user_id'] and not is_admin():
        flash('您无权查看此报名', 'danger')
        return redirect(url_for('dashboard'))
    
    competition = Competition.query.get(registration.competition_id)
    form_data = json.loads(registration.form_data)
    
    return render_template('registration_detail.html', 
                          registration=registration,
                          competition=competition,
                          form_data=form_data)

# 管理员路由
@app.route('/admin')
def admin_dashboard():
    if not is_admin():
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    users = User.query.all()
    competitions = Competition.query.all()
    notices = Notice.query.all()
    schedules = Schedule.query.all()
    registrations = Registration.query.all()
    
    # 创建映射
    user_map = {user.id: user for user in users}
    comp_map = {comp.id: comp for comp in competitions}
    
    return render_template('admin/dashboard.html', 
                          users=users,
                          competitions=competitions,
                          notices=notices,
                          schedules=schedules,
                          registrations=registrations,
                          user_map=user_map,
                          comp_map=comp_map)

@app.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # 添加新用户
        username = request.form['username']
        password = request.form['password']
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        team_name = request.form.get('team_name', '')  # 新增队伍名称
        province = request.form.get('province', '')    # 新增省份
        is_admin = 'is_admin' in request.form
        
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('manage_users'))
        
        new_user = User(
            username=username,
            password=password,
            name=name,
            email=email,
            phone=phone,
            team_name=team_name,
            province=province,
            is_admin=is_admin
        )
        
        db.session.add(new_user)
        db.session.commit()
        flash('用户添加成功', 'success')
        return redirect(url_for('manage_users'))
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:id>/edit', methods=['GET', 'POST'])
def edit_user(id):
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        # 更新用户信息
        user.name = request.form.get('name', '')
        user.email = request.form.get('email', '')
        user.phone = request.form.get('phone', '')
        user.team_name = request.form.get('team_name', '')  # 新增队伍名称
        user.province = request.form.get('province', '')    # 新增省份
        user.is_admin = 'is_admin' in request.form
        
        # 如果提供了新密码
        new_password = request.form.get('password', '')
        if new_password:
            user.password = new_password
        
        db.session.commit()
        flash('用户信息更新成功', 'success')
        return redirect(url_for('manage_users'))
    
    return render_template('admin/edit_user.html', user=user)

@app.route('/admin/competitions', methods=['GET', 'POST'])
def manage_competitions():
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # 创建新比赛
        title = request.form['title']
        description = request.form['description']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
        
        # 处理表单字段
        fields = []
        for i in range(1, 6):  # 最多5个字段
            field_name = request.form.get(f'field_name_{i}', '')
            field_type = request.form.get(f'field_type_{i}', '')
            if field_name and field_type:
                field_data = {
                    'name': field_name,
                    'type': field_type,
                    'required': f'field_required_{i}' in request.form
                }
                
                # 如果字段类型是下拉选择，添加选项
                if field_type == 'select':
                    options = request.form.get(f'field_options_{i}', '')
                    field_data['options'] = options
                
                fields.append(field_data)
        
        new_competition = Competition(
            title=title,
            description=description,
            start_date=start_date,
            end_date=end_date,
            form_fields=json.dumps(fields, ensure_ascii=False)
        )
        
        db.session.add(new_competition)
        db.session.commit()
        flash('比赛创建成功', 'success')
        return redirect(url_for('manage_competitions'))
    
    competitions = Competition.query.all()
    return render_template('admin/competitions.html', competitions=competitions)

@app.route('/admin/notices', methods=['GET', 'POST'])
def manage_notices():
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # 创建新通知
        title = request.form['title']
        content = request.form['content']
        is_public = 'is_public' in request.form
        user_id = request.form.get('user_id', None)
        
        if user_id == '0':
            user_id = None
        
        new_notice = Notice(
            title=title,
            content=content,
            is_public=is_public,
            user_id=user_id
        )
        
        db.session.add(new_notice)
        db.session.commit()
        flash('通知发布成功', 'success')
        return redirect(url_for('manage_notices'))
    
    notices = Notice.query.all()
    users = User.query.all()
    return render_template('admin/notices.html', notices=notices, users=users)

@app.route('/admin/schedules', methods=['GET', 'POST'])
def manage_schedules():
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # 创建新赛程安排
        title = request.form['title']
        content = request.form['content']
        start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
        user_id = request.form['user_id']
        competition_id = request.form.get('competition_id', None)
        
        if competition_id == '0':
            competition_id = None
        
        new_schedule = Schedule(
            title=title,
            content=content,
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            competition_id=competition_id
        )
        
        db.session.add(new_schedule)
        db.session.commit()
        flash('赛程安排发布成功', 'success')
        return redirect(url_for('manage_schedules'))
    
    schedules = Schedule.query.all()
    users = User.query.all()
    competitions = Competition.query.all()
    return render_template('admin/schedules.html', 
                          schedules=schedules,
                          users=users,
                          competitions=competitions)

@app.route('/admin/registrations')
def manage_registrations():
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    registrations = Registration.query.all()
    users = {user.id: user for user in User.query.all()}
    competitions = {comp.id: comp for comp in Competition.query.all()}
    
    return render_template('admin/registrations.html', 
                          registrations=registrations,
                          users=users,
                          competitions=competitions)

@app.route('/admin/registration/<int:id>/update', methods=['POST'])
def update_registration_status(id):
    if not 'is_admin' in session and session['is_admin']:
        flash('无权访问管理员页面', 'danger')
        return redirect(url_for('home'))
    
    registration = Registration.query.get_or_404(id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'confirmed', 'rejected']:
        registration.status = new_status
        db.session.commit()
        flash('报名状态已更新', 'success')
    else:
        flash('无效的状态', 'danger')
    
    return redirect(url_for('manage_registrations'))

if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True)