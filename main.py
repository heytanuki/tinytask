import json
import datetime
import time
import httplib2
import uuid
from apiclient import discovery
from oauth2client import client
from flask import Flask, render_template, request, redirect, url_for, session
from tasklist import TaskDB, UserTasks, TaskItem
from conf.secrets import GOOGLE_SCOPES, APP_SECRET_KEY

app = Flask(__name__)
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

@app.route('/callback')
def get_google_oauth():
    flow = client.flow_from_clientsecrets(
        'conf/nklist_client_secret.json',
        scope=' '.join(GOOGLE_SCOPES),
        redirect_uri=url_for('get_google_oauth', _external=True),
    )
    if 'code' not in request.args:
        auth_uri = flow.step1_get_authorize_url()
        return redirect(auth_uri)
    else:
        auth_code = request.args.get('code')
        credentials = flow.step2_exchange(auth_code)
        http_auth = credentials.authorize(httplib2.Http())
        oauth2_service = discovery.build('oauth2', 'v2', http_auth)
        id = oauth2_service.userinfo().get().execute()
        email = id['email']
        user_id = email.replace('.', '')
        session['tinytask_username'] = user_id
        return redirect('/')

###########
# Helpers #
###########

def get_x_days_difference(day, x):
    date = datetime.datetime.strptime(day, '%Y%m%d')
    diff = date + datetime.timedelta(days=x)
    return diff.strftime('%Y%m%d')

def date_is_valid(date):
    if not date:
        return False
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
def get_local_time_page():
    return render_template('get_date.html') # find a better way to do this plz

@app.route('/date/<date>/')
def render_tasklist(date=None):
    if 'tinytask_username' not in session:
        return redirect(url_for('get_google_oauth'))
    username = session['tinytask_username']
    user_tasks = UserTasks(username, task_db)
    if date is not None:
        if date_is_in_past(date):
            return render_past_tasklist(date)
    if date is None:
        date = get_today()
    if not date_is_valid(date):
        return redirect(url_for('render_tasklist', date=None))
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
    return render_template('task_list.html', tasks=tasks_ordered, date=date, time_loaded=int(time.time()), logged_in_as=username)

def render_past_tasklist(date):
    if 'tinytask_username' not in session:
        return redirect(url_for('get_google_oauth'))
    username = session['tinytask_username']
    user_tasks = UserTasks(username, task_db)
    tasks = user_tasks.tasks_for_day(date)
    return render_template('task_list_past.html', tasks=tasks, date=date, logged_in_as=username)

@app.route('/phil/')
def philosophy():
    return render_template('philosophy.html')

@app.route('/demo/')
def render_demo():
    pass

@app.route('/insert/', methods=['POST'])
def insert_from_form():
    description = request.form.get('description')
    date_due = request.form.get('date_due', None)
    redir_date = date_due
    if not date_due:
        date_due = get_today()
    insert_from_api(description, date_due)
    return redirect(url_for('render_tasklist', date=redir_date))


###############
# API METHODS #
###############

@app.route('/tasklist/need_to_refresh/', methods=['GET'])
def need_to_refresh():
    if 'tinytask_username' not in session:
        return redirect(url_for('get_google_oauth'))
    username = session['tinytask_username']
    user_tasks = UserTasks(username, task_db)
    date = request.args.get('date')
    loaded_time = int(request.args.get('page_load_time'))
    last_updated = user_tasks.get_last_updated_time(date)
    if last_updated > loaded_time:
        return "true"
    else:
        return "false"

@app.route('/tasklist/insert/', methods=['POST'])
def insert_from_api(description=None, date_due=None):
    if 'tinytask_username' not in session:
        return redirect(url_for('get_google_oauth'))
    username = session['tinytask_username']
    if description is None and date_due is None:
        date_due = request.form.get('date_due', None)
        description = request.form.get('description')
    new_task = TaskItem(username, task_db, date_due=date_due, description=description)
    return "ok"

@app.route('/tasklist/advance/', methods=['POST'])
def advance_from_api():
    task = parse_task(request)
    task.advance()
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/undo/', methods=['POST'])
def undo_from_api():
    task = parse_task(request)
    task.advance(reset=True)
    return 'ok'

@app.route('/tasklist/moveto/', methods=['POST'])
def move_to_x_days():
    x_days = request.form.get('x_days', None)
    task = parse_task(request)
    new_date = get_x_days_difference(task.date_due, int(x_days))
    task.update({'date_due': new_date})
    return 'ok'

@app.route('/tasklist/details/', methods=['GET'])
def details_from_api():
    task = parse_task(request)
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/delete/', methods=['POST'])
def delete_from_api():
    task = parse_task(request)
    task.delete()
    return 'ok'

def parse_task(request):
    if 'tinytask_username' not in session:
        return redirect(url_for('get_google_oauth'))
    username = session['tinytask_username']
    if request.method == 'POST':
        date = request.form.get('date_due')
        task_key = request.form.get('task_key')
    if request.method == 'GET':
        date = request.args.get('date_due')
        task_key = request.args.get('task_key')
    task = TaskItem(username, task_db, date, task_key)
    return task

if __name__ == '__main__':
    app.secret_key = APP_SECRET_KEY
    app.run(host='0.0.0.0', port=8080, debug=True)
