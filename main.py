import json
import datetime
import time
import httplib2
import uuid
import flask
import re
from flask_sslify import SSLify
from apiclient import discovery
from oauth2client import client
from tasklist import TaskDB, UserTasks, TaskItem, TaskError
from tasklist_util import get_x_days_difference, date_is_valid, date_is_in_current_range, get_today
from conf.secrets import GOOGLE_SCOPES, GOOGLE_CLIENT_SECRET_PATH, APP_SECRET_KEY, APP_SECRET_KEY_PROD, AUTHORIZED_EMAILS

app = flask.Flask(__name__)
app.secret_key = APP_SECRET_KEY_PROD
sslify = SSLify(app, permanent=True)
task_db = TaskDB()

SUCCESS_RESPONSE = (json.dumps({'success':True}), 200, {'ContentType':'application/json'})
SVG_LINK_ARROW = """
<svg class="out_link" width="22" height="22">
    <line x1="5" y1="20" x2="20" y2="5" />
    <path stroke-width="2px" stroke-linecap="round" stroke-linejoin="round" fill="transparent" d="M 10 5 h 10 v 10" />
</svg>
"""

@app.context_processor
def context_proc():
    def goto_x_days_difference(day, x):
        return get_x_days_difference(day, x)

    def get_readable_date(date):
        date_parsed = datetime.datetime.strptime(date, '%Y%m%d')
        return date_parsed.strftime('%a %-m/%-d')

    def parse_links(description):
        matches = re.findall("(?P<url>https?://[^\s]+)", description)
        if not matches:
            return description
        else:
            desc_with_links = description
            for m in matches:
                desc_with_links = desc_with_links.replace(m, '<a class="out_link" target="_blank" href="{0}">{1}</a>'.format(m, SVG_LINK_ARROW))
            return desc_with_links

    return dict(
        get_days=goto_x_days_difference,
        get_readable_date=get_readable_date,
        parse_links=parse_links,
    )

##################
# Authentication #
##################

# TODO: figure out a decorator to simplify testing login status

@app.route('/callback/')
def get_google_oauth():
    flow = client.flow_from_clientsecrets(
        GOOGLE_CLIENT_SECRET_PATH,
        scope=' '.join(GOOGLE_SCOPES),
        redirect_uri=flask.url_for('get_google_oauth', _external=True),
    )
    if 'code' not in flask.request.args:
        auth_uri = flow.step1_get_authorize_url()
        return flask.redirect(auth_uri)
    else:
        auth_code = flask.request.args.get('code')
        credentials = flow.step2_exchange(auth_code)
        http_auth = credentials.authorize(httplib2.Http())
        oauth2_service = discovery.build('oauth2', 'v2', http=http_auth)
        id = oauth2_service.userinfo().get().execute()
        email = id['email']
        user_id = get_user_id(email)
        if not user_id:
            return flask.redirect(flask.url_for('not_authorized'))
        flask.session['tinytask_username'] = user_id
        return flask.redirect(flask.url_for('render_today'))

def get_user_id(email):
    if email not in AUTHORIZED_EMAILS:
        with open('tried_to_oauth.txt', 'a+') as f:
            f.write(email + '\n')
        return False
    user_id = email.replace('.', '')
    user_db = UserTasks(user_id, task_db)
    settings = user_db.get_user_settings()
    if settings is None:
        user_db.set_user_setting('email', email)
        user_db.set_user_setting('secret', str(uuid.uuid4()))
        return user_id
    if 'email' in settings:
        if email != settings['email']:
            return False
    else:
        user_db.set_user_setting('email', email)
    return user_id

def initialize_user(email, user_db):
    user_db.set_user_setting('email', email)
    user_db.set_user_setting('secret', str(uuid.uuid4()))

###########
# Helpers #
###########

def date_is_in_past(date):
    today_date = datetime.datetime.strptime(get_today(), '%Y%m%d')
    loaded_date = datetime.datetime.strptime(date, '%Y%m%d')
    delta = today_date - loaded_date
    if delta.days > 1:
        return True
    return False

def get_stats_on(task_list):
    statuses = {
        'notdone': 0,
        'started': 0,
        'done': 0,
    }
    total = 0
    for task in task_list:
        try:
            statuses[task['status']] += 1
        except KeyError:
            continue
        except TypeError:
            continue
        total += 1
    complete = float(statuses['done']) / float(total) * 100
    return {
        'total': total,
        'statuses': statuses,
        'complete': complete,
    }

def sort_started_first(tasklist):
    tasks_by_type = {
        'started': [],
        'notdone': [],
        'done': []
    }
    for task in tasklist:
        try:
            tasks_by_type[task['status']].append(task)
        except KeyError:
            continue
    tasks_ordered = tasks_by_type['started'] + tasks_by_type['notdone'] + tasks_by_type['done']
    return tasks_ordered

#########
# Routes #
#########

@app.route('/')
def index():
    username = flask.session.get('tinytask_username', None)
    if username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    content = """
        is being tested right now. 
        <p>If you've been invited, <a href="/callback/" class="underlined">go here to log in with Google</a>.</p>
        <p>Tinytask uses your Google account for authentication purposes only. 
        Your user information will remain private.
        <p><a href="/info/" class="underlined">More info!</a>"""
    return flask.render_template('index.html', content=content)

@app.route('/login/')
def render_login():
    return flask.render_template('login.html')

@app.route('/date/')
def render_today():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    return flask.render_template('today.html')

@app.route('/date/<date>/')
def render_tasklist(date):
    if not date_is_valid(date) or not date_is_in_current_range(date):
        return flask.redirect(flask.url_for('render_today'))
    if date_is_in_past(date):
        return render_past_tasklist(date)

    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db)
    user_settings = user_tasks.get_user_settings()

    tasks = user_tasks.get_task_group(date)
    sort_option = user_settings.get('Sorting', None)
    if sort_option is None or sort_option == 'Started first':
        tasks_ordered = sort_started_first(tasks)
    if sort_option == 'Chronological':
        tasks_ordered = tasks
    return flask.render_template(
        'task_list.html',
        tasks=tasks_ordered,
        date=date,
        time_loaded=int(time.time()),
    )

@app.route('/mock/')
def render_mock_tasklist():
    date = get_today()
    tasks = [
        {
            'description': 'thing 1',
            'status': 'done',
            'date_or_project': '20171031',
            'timestamp': 1,
        },
        {
            'description': 'thing 2',
            'status': 'notdone',
            'date_or_project': '20171031',
            'timestamp': 2,
        },
        {
            'description': 'thing 3',
            'status': 'notdone',
            'date_or_project': '20171031',
            'timestamp': 3,
        },
        {
            'description': 'thing 4',
            'status': 'started',
            'date_or_project': '20171031',
            'timestamp': 4,
        },
    ]
    
    return flask.render_template(
        'mock_task_list.html',
        tasks=tasks,
        date=date,
        time_loaded=int(time.time()),
    )

def render_past_tasklist(date):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db)
    tasks = user_tasks.get_task_group(date)
    return flask.render_template('task_list_past.html', tasks=tasks, date=date, logged_in_as=username)

@app.route('/project/')
def render_projects_page():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db, tasks_database='projects')
    projects = user_tasks.get_all_dates_or_projects()
    return flask.render_template('projects.html', projects=projects)
    # TODO develop a projects list template

@app.route('/project/<project_name>/')
def render_project(project_name):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db, tasks_database='projects')
    tasks = user_tasks.get_task_group()
    tasks_ordered = sort_started_first(tasks)
    return flask.render_template(
        'project_task_list.html',
        tasks=tasks_ordered,
        project=project_name,
        time_loaded=int(time.time()),
    )
    # TODO develop a project view

@app.route('/settings/')
def render_settings():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db)
    settings = user_tasks.get_user_settings()
    return flask.render_template('settings.html', settings=settings)

@app.route('/noauth/')
def not_authorized():
    flask.session.clear()
    return flask.render_template('index.html', content=""" is not accessible or you've been logged out. <a href="/date/" class="underlined">Log in</a> if you're authorized.""")

################
# Simple pages #
################

@app.route('/info/')
def show_info():
    return flask.render_template('info.html')

@app.route('/phil/')
def philosophy():
    return flask.render_template('philosophy.html')

@app.route('/demo/')
def render_demo():
    return flask.render_template('demo.html')

@app.route('/icon/')
def send_icon():
    return flask.send_file('static/tinytask_icon_logo.png', mimetype='image/png')

@app.route('/wack/')
def render_wack():
    return flask.render_template('wack.html')

###############
# API METHODS #
###############

@app.route('/tasklist/need_to_refresh/', methods=['GET'])
def need_to_refresh():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db)
    date_or_project = flask.request.args.get('date_or_project')
    loaded_time = int(flask.request.args.get('page_load_time'))
    last_updated = user_tasks.get_last_updated_time(date_or_project)
    if last_updated > loaded_time:
        return "true"
    else:
        return "false"

@app.route('/tasklist/insert/', methods=['POST'])
def insert_from_api(description=None, date_or_project=None):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    if description is None and date_or_project is None:
        date_or_project = flask.request.form.get('date_or_project', None)
        description = flask.request.form.get('description')
    user_db = UserTasks(username, task_db)
    new_task = TaskItem(user_db, date_or_project=date_or_project, description=description)
    return SUCCESS_RESPONSE

@app.route('/tasklist/update/', methods=['POST'])
def update_from_api():
    task = parse_task(flask.request)
    field = flask.request.form.get('field', None)
    value = flask.request.form.get('value', None)
    if not field:
        return (json.dumps({'success': False}), 400, {'ContentType':'application/json'})
    if field and not value:
        value = ''
    task.update({field: value})
    return SUCCESS_RESPONSE

@app.route('/tasklist/advance/', methods=['POST'])
def advance_from_api():
    task = parse_task(flask.request)
    task.advance()
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/undo/', methods=['POST'])
def undo_from_api():
    task = parse_task(flask.request)
    task.advance(reset=True)
    return SUCCESS_RESPONSE

@app.route('/tasklist/moveto/', methods=['POST'])
def move_to_x_days():
    x_days = flask.request.form.get('x_days', None)
    task = parse_task(flask.request)
    if not date_is_valid(task.date_or_project):
        raise TaskError('Cannot move a project task x days.')
    new_date = get_x_days_difference(task.date_or_project, int(x_days))
    task.update({'date_or_project': new_date})
    return SUCCESS_RESPONSE

@app.route('/tasklist/details/', methods=['GET'])
def details_from_api():
    task = parse_task(flask.request)
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/delete/', methods=['POST'])
def delete_from_api():
    task = parse_task(flask.request)
    task.delete()
    return SUCCESS_RESPONSE

def parse_task(current_request):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    if current_request.method == 'POST':
        date_or_project = current_request.form.get('date_or_project')
        task_key = current_request.form.get('task_key')
    if current_request.method == 'GET':
        date_or_project = current_request.args.get('date_or_project')
        task_key = current_request.args.get('task_key')
    user_db = UserTasks(username, task_db)
    task = TaskItem(user_db, date_or_project, task_key)
    return task

@app.route('/test/')
def render_test():
    return flask.render_template('webctest_task-item.html')

@app.route('/status/')
def render_statuses():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    today = get_today()
    past_7_days = [get_x_days_difference(today, x) for x in range(-6,1)]
    user_tasks = UserTasks(username, task_db)
    user_secret = user_tasks.get_user_settings('secret')
    tasks = []
    for day in past_7_days:
        tasks += user_tasks.get_task_group(day)
    all_tasks = user_tasks.get_all_tasks()
    stats = get_stats_on(tasks)
    all_time_count = get_stats_on(all_tasks)['total']
    return flask.render_template(
        'status.html',
        tasks=tasks,
        stats=stats,
        all_time_count=all_time_count,
        user_secret=user_secret,
    )

if __name__ == '__main__':
    app.secret_key = APP_SECRET_KEY
    app.run(host='0.0.0.0', port=8080, debug=True)
