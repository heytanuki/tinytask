import json
import datetime
import time
from flask import Flask, render_template, request, redirect
from tasklist import TaskDB, TaskItem

app = Flask(__name__)
task_db = TaskDB()

@app.context_processor
def context_proc():
    def goto_x_days_difference(day, x):
        return task_db.get_x_days_difference(day, x)

    def get_readable_date(date):
        date_parsed = datetime.datetime.strptime(date, '%Y%m%d')
        return date_parsed.strftime('%a %-m/%-d')
    return dict(
        get_days=goto_x_days_difference,
        get_readable_date=get_readable_date,
    )

def date_is_valid(date):
    if not date:
        return False
    try:
        date_parsed = datetime.datetime.strptime(date, '%Y%m%d')
        return True
    except ValueError:
        return False

@app.route('/')
def get_local_time_page():
    print 'getting local time'
    return render_template('get_date.html')

@app.route('/<date>')
def render_tasklist(date=None):
    if date is None:
        date = task_db.get_today()
    if not date_is_valid(date):
        return redirect('/')
    tasks = task_db.tasks_for_day(date)
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

@app.route('/phil')
def philosophy():
    return render_template('philosophy.html')

@app.route('/demo')
def render_demo():
    pass

@app.route('/insert', methods=['POST'])
def insert_from_form():
    description = request.form.get('description')
    date_due = request.form.get('date_due', None)
    redir_date = date_due
    if not date_due:
        date_due = task_db.get_today()
    insert_from_api(description, date_due)
    return redirect('/{}'.format(redir_date))


###############
# API METHODS #
###############

@app.route('/tasklist/need_to_refresh', methods=['GET'])
def need_to_refresh():
    date = request.args.get('date')
    loaded_time = int(request.args.get('page_load_time'))
    last_updated = task_db.get_last_updated_time(date)
    print '{}: {}'.format(type(loaded_time), loaded_time)
    print '{}: {}'.format(type(last_updated), last_updated)
    if last_updated > loaded_time:
        return "true"
    else:
        return "false"

@app.route('/tasklist/insert', methods=['POST'])
def insert_from_api(description=None, date_due=None):
    if description is None and date_due is None:
        date_due = request.form.get('date_due', None)
        description = request.form.get('description')
    new_task = TaskItem(date_due=date_due, description=description)
    return "ok"

@app.route('/tasklist/advance', methods=['POST'])
def advance_from_api():
    task = parse_task(request)
    task.advance()
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/undo', methods=['POST'])
def undo_from_api():
    task = parse_task(request)
    task.advance(reset=True)
    return 'ok'

@app.route('/tasklist/moveto', methods=['POST'])
def move_to_x_days():
    x_days = request.form.get('x_days', None)
    task = parse_task(request)
    new_date = task_db.get_x_days_difference(task.date_due, int(x_days))
    task.update({'date_due': new_date})
    return 'ok'

@app.route('/tasklist/details', methods=['GET'])
def details_from_api():
    task = parse_task(request)
    output = task.details()
    return json.dumps(output)

@app.route('/tasklist/delete', methods=['POST'])
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
    task = TaskItem(date, task_key)
    return task

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
