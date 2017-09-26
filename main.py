import json
import datetime
import time
import httplib2
import uuid
from apiclient import discovery
from oauth2client import client
import flask
from tasklist import TaskDB, UserTasks, TaskItem
from conf.secrets import GOOGLE_SCOPES, GOOGLE_CLIENT_SECRET_PATH, APP_SECRET_KEY, APP_SECRET_KEY_PROD, AUTHORIZED_EMAILS

app = flask.Flask(__name__)
app.secret_key = APP_SECRET_KEY_PROD
task_db = TaskDB()

@app.context_processor
def context_proc():
    def goto_x_days_difference(day, x):
        return get_x_days_difference(day, x)

    def get_readable_date(date):
        date_parsed = datetime.datetime.strptime(date, '%Y%m%d')
        return date_parsed.strftime('%a %-m/%-d')

    return dict(
        get_days=goto_x_days_difference,
        get_readable_date=get_readable_date,
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
        oauth2_service = discovery.build('oauth2', 'v2', http_auth)
        id = oauth2_service.userinfo().get().execute()
        email = id['email']
        if email not in AUTHORIZED_EMAILS:
            return flask.redirect(flask.url_for('not_authorized'))
        user_id = email.replace('.', '')
        flask.session['tinytask_username'] = user_id
        return flask.redirect(flask.url_for('render_today'))

###########
# Helpers #
###########

def get_x_days_difference(day, x):
    date = datetime.datetime.strptime(day, '%Y%m%d')
    diff = date + datetime.timedelta(days=x)
    return diff.strftime('%Y%m%d')

def date_is_valid(date):
    try:
        date_parsed = datetime.datetime.strptime(date, '%Y%m%d')
        return True
    except ValueError:
        return False

def get_today():
    return datetime.date.today().isoformat().replace('-', '')

def date_is_in_past(date):
    today_date = datetime.datetime.strptime(get_today(), '%Y%m%d')
    loaded_date = datetime.datetime.strptime(date, '%Y%m%d')
    delta = today_date - loaded_date
    if delta.days > 1:
        return True
    return False

##########
# Routes #
##########

@app.route('/')
def index():
    username = flask.session.get('tinytask_username', None)
    if username:
        return flask.redirect(flask.url_for('render_today'))
    content = """
        is being tested right now. 
        <p>If you've been invited, <a href="/callback/">go here to log in with Google</a>.</p>
        <p>Tinytask uses your Google account for authentication purposes only. 
        Your user information will remain private.
        <p><a href="/info/">More info!</a>"""
    return flask.render_template('index.html', content=content)

@app.route('/date/')
def render_today():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    return flask.render_template('today.html')

@app.route('/date/<date>/')
def render_tasklist(date):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    if not date_is_valid(date):
        return flask.redirect(flask.url_for('render_today'))
    user_tasks = UserTasks(username, task_db)
    if date_is_in_past(date):
        return render_past_tasklist(date)
    tasks = user_tasks.tasks_for_day(date)
    tasks_by_type = {
        'started': [],
        'notdone': [],
        'done': []
    }
    for task in tasks:
        try:
            tasks_by_type[task['status']].append(task)
        except KeyError:
            continue
    tasks_ordered = tasks_by_type['started'] + tasks_by_type['notdone'] + tasks_by_type['done']
    return flask.render_template('task_list.html', tasks=tasks_ordered, date=date, time_loaded=int(time.time()), logged_in_as=username)

def render_past_tasklist(date):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db)
    tasks = user_tasks.tasks_for_day(date)
    return flask.render_template('task_list_past.html', tasks=tasks, date=date, logged_in_as=username)

@app.route('/info/')
def show_info():
    return flask.render_template('info.html')

@app.route('/phil/')
def philosophy():
    return flask.render_template('philosophy.html')

@app.route('/demo/')
def render_demo():
    return flask.render_template('demo.html')

@app.route('/insert/', methods=['POST'])
def insert_from_form():
    description = flask.request.form.get('description', None)
    date_due = flask.request.form.get('date_due', None)
    if not description:
        return flask.redirect(flask.url_for('render_tasklist', date=date_due))
    redir_date = date_due
    if not date_due:
        date_due = get_today()
    insert_from_api(description, date_due)
    return flask.redirect(flask.url_for('render_tasklist', date=redir_date))

@app.route('/noauth/')
def not_authorized():
    flask.session.pop('tinytask_username', None)
    return flask.render_template('index.html', content=""" is not accessible, for now.""")

@app.route('/icon/')
def send_icon():
    return flask.send_file('static/tinytask_icon_logo.png', mimetype='image/png')

###############
# API METHODS #
###############

@app.route('/tasklist/need_to_refresh/', methods=['GET'])
def need_to_refresh():
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    user_tasks = UserTasks(username, task_db)
    date = flask.request.args.get('date')
    loaded_time = int(flask.request.args.get('page_load_time'))
    last_updated = user_tasks.get_last_updated_time(date)
    if last_updated > loaded_time:
        return "true"
    else:
        return "false"

@app.route('/tasklist/insert/', methods=['POST'])
def insert_from_api(description=None, date_due=None):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    if description is None and date_due is None:
        date_due = flask.request.form.get('date_due', None)
        description = flask.request.form.get('description')
    new_task = TaskItem(username, task_db, date_due=date_due, description=description)
    return "ok"

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
    return 'ok'

@app.route('/tasklist/moveto/', methods=['POST'])
def move_to_x_days():
    x_days = flask.request.form.get('x_days', None)
    task = parse_task(flask.request)
    new_date = get_x_days_difference(task.date_due, int(x_days))
    task.update({'date_due': new_date})
    return 'ok'

@app.route('/tasklist/details/', methods=['GET'])
def details_from_api():
    task = parse_task(flask.request)
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/delete/', methods=['POST'])
def delete_from_api():
    task = parse_task(flask.request)
    task.delete()
    return 'ok'

def parse_task(current_request):
    username = flask.session.get('tinytask_username', None)
    if not username:
        return flask.redirect(flask.url_for('get_google_oauth'))
    if current_request.method == 'POST':
        date = current_request.form.get('date_due')
        task_key = current_request.form.get('task_key')
    if current_request.method == 'GET':
        date = current_request.args.get('date_due')
        task_key = current_request.args.get('task_key')
    task = TaskItem(username, task_db, date, task_key)
    return task

if __name__ == '__main__':
    app.secret_key = APP_SECRET_KEY
    app.run(host='0.0.0.0', port=8080, debug=True)
