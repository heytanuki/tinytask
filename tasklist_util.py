import datetime
from tasklist import TaskDB, UserTasks

db_connection = TaskDB()

DATES_LIMIT = 50
ERROR_LOG_FILE = 'error_log.txt'

##################
# Database utils #
##################

def run_daily_maintenance():
    users = db_connection.get_users()
    error_log = {}
    for user in users:
        move_old_entries_to_archive(user)
        cleanup_empty_dates(user)
        result = check_user_database(user)
        if result:
            error_log[user] = result
    if error_log:
        write_error_log(error_log)
        
def write_error_log(errors_dict):
    filename = ERROR_LOG_FILE
    output_lines = []
    for header in errors_dict:
        for statement in errors_dict[header]:
            prefix = datetime.datetime.now().strftime('%Y/%m/%d %H:%M - ')
            line = '{}{}'.format(prefix, statement)
            output_lines.append(line)
    with open(ERROR_LOG_FILE, 'a+') as f:
        for line in output_lines:
            f.write('{}{}'.format(line, '\n'))


def move_old_entries_to_archive(username):
    user_database = UserTasks(username, db_connection)
    all_dates = user_database.get_all_dates_or_projects()
    dates_to_archive = [d for d in all_dates if not date_is_in_current_range(d)]
    for date in dates_to_archive:
        print 'will archive group {}'.format(date)
        user_database.archive_group(date)

def cleanup_empty_dates(username):
    user_database = UserTasks(username, db_connection)
    all_dates = user_database.get_all_dates_or_projects()
    for date in all_dates:
        count = len(user_database.get_task_group(date))
        if count == 0:
            print 'will remove empty group {}'.format(date)
            user_database.delete_group(date)

def check_user_database(username):
    """ Omnibus check. Doesn't do anything but report. """
    """ Detects too many groups, non-date date headings, empty groups, date_due, date mismatch"""
    user_database = UserTasks(username, db_connection)
    error_log = []
    groups = user_database.get_all_dates_or_projects()
    if len(groups) > DATES_LIMIT:
        error_log.append('{} has more than {} dates.'.format(username, DATES_LIMIT))
    for group in groups:
        if user_database.tasks_database == 'tasks' and not date_is_valid(group):
            error_log.append('{}/tasks/{} is not a date.'.format(username, group))
        tasks = user_database.get_task_group(group)
        if len(tasks) == 0:
            error_log.append('{}/tasks/{} is empty and should be removed.'.format(username, group))
        for task in tasks:
            if 'date_due' in task:
                error_log.append('{}/{}/{} has date_due.'.format(username, group, task['task_key']))
            date_from_task = task.get('date_or_project', '<none>')
            if date_from_task != group:
                error_log.append('{}/{}/{} date mismatch.'.format(username, group, task['task_key']))
    return error_log


#####################
# Date format utils #
#####################

def date_is_in_current_range(date):
    if not date_is_valid(date):
        return False
    today = get_today()
    earliest = int(get_x_days_difference(today, -30))
    latest = int(get_x_days_difference(today, 3650))
    if int(date) < latest and int(date) > earliest:
        return True
    return False

def get_x_days_difference(day, x):
    date = datetime.datetime.strptime(day, '%Y%m%d')
    diff = date + datetime.timedelta(days=x)
    return diff.strftime('%Y%m%d')

def date_is_valid(date):
    try:
        if int(date[0:4]) < 1900:
            return False
        date_parsed = datetime.datetime.strptime(date, '%Y%m%d')
        return True
    except ValueError:
        return False

def get_today():
    return datetime.date.today().isoformat().replace('-', '')