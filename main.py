import json
import datetime
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

@app.route('/tasklist/getdatestatus', methods=['GET'])
def get_date_status():
    date = request.args.get('date')
    if not date_is_valid(date):
        return 'started'
    return get_overall_status(task_db.tasks_for_day(date))

def get_overall_status(tasks):
    tasks_done = len([task['status'] for task in tasks if task['status'] == 'done'])
    if len(tasks) == 0:
        return 'notdone' 
    if tasks_done == len(tasks):
        return 'done'    
    return 'started'

@app.route('/')
@app.route('/<date>')
def render_tasklist(date=None):
    if date is None:
        date = task_db.get_today()
    if not date_is_valid(date):
        return redirect('/')
    tasks = task_db.tasks_for_day(date)
    date_status = get_overall_status(tasks)
    return render_template('task_list.html', tasks=tasks, date=date, date_status=date_status)

@app.route('/insert', methods=['POST'])
def insert_from_form():
    description = request.form.get('description')
    date_due = request.form.get('date_due', None)
    redir_date = date_due
    if not date_due:
        date_due = task_db.get_today()
    insert_from_api(description, date_due)
    return redirect('/{}'.format(redir_date))

# test method, kill this one
@app.route('/reset/<date>')
def reset_day(date):
    tasks = task_db.tasks_for_day(date)
    for task in tasks:
        item = TaskItem(task['date_due'], task['task_key'])
        item.advance(reset=True)
    return redirect('/{}'.format(date))

###############
# API METHODS #
###############

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