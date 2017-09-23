import json
import datetime
import time
from flask import Flask, render_template, request, redirect
from tasklist import TaskDB, UserTasks, TaskItem

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
    print delta.days
    if delta.days > 1:
        return True
    return False

##########
# Routes #
##########

@app.route('/')
def get_local_time_page():
    return render_template('get_date.html')

@app.route('/date/<date>/')
def render_tasklist(date=None):
    user_tasks = UserTasks('tanuki', task_db)
    if date is not None:
        if date_is_in_past(date):
            return render_past_tasklist(date)
    if date is None:
        date = get_today()
    if not date_is_valid(date):
        return redirect('/date/')
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
    return render_template('task_list.html', tasks=tasks_ordered, date=date, time_loaded=int(time.time()))

def render_past_tasklist(date):
    user_tasks = UserTasks('tanuki', task_db)
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
    return render_template('task_list_past.html', tasks=tasks_ordered, date=date, time_loaded=int(time.time()))

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
    return redirect('/date/{}'.format(redir_date))


###############
# API METHODS #
###############

@app.route('/tasklist/need_to_refresh/', methods=['GET'])
def need_to_refresh():
    user_tasks = UserTasks('tanuki', task_db)
    date = request.args.get('date')
    loaded_time = int(request.args.get('page_load_time'))
    last_updated = user_tasks.get_last_updated_time(date)
    if last_updated > loaded_time:
        return "true"
    else:
        return "false"

@app.route('/tasklist/insert/', methods=['POST'])
def insert_from_api(description=None, date_due=None):
    if description is None and date_due is None:
        date_due = request.form.get('date_due', None)
        description = request.form.get('description')
    new_task = TaskItem('tanuki', task_db, date_due=date_due, description=description)
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
    if request.method == 'POST':
        date = request.form.get('date_due')
        task_key = request.form.get('task_key')
    if request.method == 'GET':
        date = request.args.get('date_due')
        task_key = request.args.get('task_key')
    task = TaskItem('tanuki', task_db, date, task_key)
    return task

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
