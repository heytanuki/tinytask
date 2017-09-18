import pyrebase
import datetime
from secrets import FIREBASE_CONFIG, FIREBASE_AUTH_USER, FIREBASE_AUTH_PW


class TaskError(Exception):
    pass


class TaskDB(object):

    def __init__(self, tasks_database='tasks'):
        self.firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
        self.auth = self.firebase.auth()
        self.do_auth()
        self.db = self.firebase.database()
        self.tasks_database = tasks_database

    def do_auth(self):
        self.user = self.auth.sign_in_with_email_and_password(FIREBASE_AUTH_USER, FIREBASE_AUTH_PW)
        expiration_timedelta = datetime.timedelta(seconds=int(self.user['expiresIn']) - 600) # trigger refresh 10 minutes early
        self.expiry_time = datetime.datetime.now() + expiration_timedelta
        self.token = self.get_token()

    def get_token(self):
        if self.expiry_time < datetime.datetime.now():
            self.refresh_user()
        return self.user['idToken']

    def refresh_user(self):
        try:
            self.user = self.auth.refresh(self.user['refreshToken'])
            expiration_timedelta = datetime.timedelta(seconds=int(self.user['expiresIn']) - 600) # trigger refresh 10 minutes early
            self.expiry_time = datetime.datetime.now() + expiration_timedelta
        except KeyError:
            self.__init__()

    def log_error(self, err_msg):
        self.db \
            .child('errors') \
            .child(err_msg) \
            .set(self.get_token())

    def get_x_days_difference(self, day, x):
        date = datetime.datetime.strptime(day, '%Y%m%d')
        diff = date + datetime.timedelta(days=x)
        return diff.strftime('%Y%m%d')

    def get_today(self):
        return datetime.date.today().isoformat().replace('-', '')

    def insert_data(self, data):
        if 'timestamp' not in data:
            data['timestamp'] = {'.sv': 'timestamp'}
        result = self.db \
                     .child(self.tasks_database) \
                     .child(data['date_due']) \
                     .push(data, self.get_token())
        return result

    def insert_task(self, description, date_due=None):
        if not date_due:
            date_due = self.get_today()
        data = {
            'description': description,
            'date_due': date_due,
            'status': 'notdone',
        }
        result = self.insert_data(data)
        return (date_due, result['name'])

    def get_task(self, date_due, task_key):
        try:
            task = self.db \
                       .child(self.tasks_database) \
                       .child(date_due) \
                       .order_by_child('$key') \
                       .equal_to(str(task_key)) \
                       .get(self.get_token()) \
                       .val()
        except IndexError:
            self.log_error('path:{}/{}'.format(date_due, task_key))
            raise TaskError('Task {} {} was not found. This has been logged.'.format(date_due, task_key))
        for key in task:
            return (key, task[key])

    def update_task(self, date_due, task_key, update_data):
        self.db.child(self.tasks_database) \
               .child(date_due) \
               .child(task_key) \
               .update(update_data, self.get_token())
        if 'date_due' in update_data:
            if update_data['date_due'] != date_due:
                old_key, task_data = self.get_task(date_due, task_key)
                result = self.insert_data(task_data)
                new_key = result['name']
                self.delete_task(date_due, task_key)
                return (update_data['date_due'], new_key)

    def delete_task(self, date_due, task_key):
        self.db.child(self.tasks_database) \
               .child(date_due) \
               .child(task_key) \
               .remove(self.get_token())

    def delete_all_tasks_for_date(self, date):
        self.db.child(self.tasks_database) \
               .child(date) \
               .remove(self.get_token())

    def tasks_to_list(self, tasks):
        tasks_as_list = []
        for item in tasks:
            task_as_dict = tasks[item]
            task_as_dict['task_key'] = item
            tasks_as_list.append(task_as_dict)
        return tasks_as_list

    def tasks_for_day(self, day):
        tasks = self.db.child(self.tasks_database) \
                       .child(day) \
                       .order_by_child('timestamp') \
                       .get(self.get_token()) \
                       .val()
        if tasks:
            return self.tasks_to_list(tasks)
        return {}

    def test_database(self, fix_errors=False):
        whole_db = self.db.child('tasks') \
                          .get(self.get_token()).val()
        error_task_paths = []
        for date in whole_db:
            for task in whole_db[date]:
                if whole_db[date][task]['date_due'] != date:
                    error_task = '{}/{}'.format(date, task)
                    error_task_paths.append(error_task)
        if len(error_task_paths) == 0:
            print "Checked database, no errors found."
            return
        if fix_errors:
            self.fix_errors(error_task_paths)
        else:
            return error_task_paths

    def fix_errors(self, paths):
        for path in paths:
            date, key = path.split('/')
            details = self.get_task(date, key)[1]
            date_due_from_task = details['date_due']
            description_from_task = details['description']
            print 'Fixing task to proper due date {}: {}'.format(date_due_from_task, description_from_task)
            self.update_task(date, key, {'date_due': date_due_from_task})


class TaskItem(object):

    def __init__(self, date_due, task_key=None, description=None):
        self.task_database = TaskDB()
        if task_key:
            self.date_due = date_due
            self.task_key = task_key
        elif description:
            self.date_due, self.task_key = self.task_database.insert_task(description, date_due)
        elif not task_key and not description:
            raise TaskError('Must provide either task_key to retrieve task, or description to create task')

    def __str__(self):
        desc = self.details()['description']
        return '{} {}: {}'.format(self.date_due, self.task_key, desc)

    def details(self):
        key, task_data = self.task_database.get_task(self.date_due, self.task_key)
        task_data['task_key'] = key
        return task_data

    def delete(self):
        self.task_database.delete_task(self.date_due, self.task_key)

    def update(self, update_data):
        result = self.task_database.update_task(self.date_due, self.task_key, update_data)
        if result:
            self.date_due, self.task_key = result

    def advance(self, done=False, reset=False):
        if reset:
            self.update({'status': 'notdone'})
            return
        task = self.details()
        if task['status'] == 'done':
            return
        if task['status'] == 'started' or done:
            self.update({'status': 'done'})
            return
        if task['status'] == 'notdone':
            self.update({'status': 'started'})
            return
        self.update({'status': 'notdone'})





