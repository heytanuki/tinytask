import datetime
import time
import pyrebase
from conf.secrets import FIREBASE_CONFIG, FIREBASE_AUTH_USER, FIREBASE_AUTH_PW

ALL_USER_SETTINGS_OPTIONS = {
    'Sorting': ['Started first', 'Chronological'],
    "Offer to forward yesterday's tasks": ['Yes', 'No'],
    'Hide done': ['Yes', 'No'],
}

DATA_SETTINGS = [
    'email',
    'secret',
]


class TaskError(Exception):
    pass

class SettingsError(Exception):
    pass


class TaskDB(object):

    def __init__(self):
        self.firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
        self.auth = self.firebase.auth()
        self.do_auth()
        self.database = self.firebase.database()

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

    def get_users(self):
        users_db = self.database \
                    .get(self.get_token()) \
                    .val()
        users = [u for u in users_db]
        return users


class UserTasks(object):

    def __init__(self, username, db_connection, tasks_database='tasks'):
        self.username = username
        self.tasks_database = tasks_database
        self.db_connection = db_connection
        self.db = self.db_connection.database

    def insert_data(self, data):
        if 'timestamp' not in data:
            data['timestamp'] = {'.sv': 'timestamp'}
        result = self.db \
                     .child(self.username) \
                     .child(self.tasks_database) \
                     .child(data['date_due']) \
                     .push(data, self.db_connection.get_token())
        self.set_last_updated_time(data['date_due'])
        return result

    def insert_task(self, description, date_due=None):
        if not date_due:
            # date_due = datetime.date.today().isoformat().replace('-', '')
            raise TaskError('Task was submitted without a date.')
        data = {
            'description': description,
            'date_due': date_due,
            'status': 'notdone',
        }
        result = self.insert_data(data)
        return (date_due, result['name'])

    def set_last_updated_time(self, date):
        update_time = int(time.time())
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date) \
            .child('last_updated') \
            .set(update_time, self.db_connection.get_token())
        return update_time

    def get_last_updated_time(self, date):
        updated_time = self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date) \
            .child('last_updated') \
            .get(self.db_connection.get_token()) \
            .val()
        if updated_time is None:
            updated_time = self.set_last_updated_time(date)
        return updated_time

    def get_task(self, date_due, task_key):
        try:
            task = self.db \
                       .child(self.username) \
                       .child(self.tasks_database) \
                       .child(date_due) \
                       .order_by_child('$key') \
                       .equal_to(str(task_key)) \
                       .get(self.db_connection.get_token()) \
                       .val()
        except IndexError:
            raise TaskError('Task {} {} could not be retrieved.'.format(date_due, task_key))
        for key in task:
            return (key, task[key])

    def update_task(self, date_due, task_key, update_data):
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_due) \
            .child(task_key) \
            .update(update_data, self.db_connection.get_token())
        self.set_last_updated_time(date_due)
        if 'date_due' in update_data:
            if update_data['date_due'] != date_due:
                old_key, task_data = self.get_task(date_due, task_key)
                result = self.insert_data(task_data)
                new_key = result['name']
                self.delete_task(date_due, task_key)
                return (update_data['date_due'], new_key)

    def delete_task(self, date_due, task_key):
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_due) \
            .child(task_key) \
            .remove(self.db_connection.get_token())
        self.set_last_updated_time(date_due)

    def delete_all_tasks_for_date(self, date):
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date) \
            .remove(self.db_connection.get_token())

    def tasks_to_list(self, tasks):
        tasks_as_list = []
        for item in tasks:
            if item == 'last_updated':
                continue
            task_as_dict = tasks[item]
            task_as_dict['task_key'] = item
            tasks_as_list.append(task_as_dict)
        tasks_as_list_sorted = sorted(tasks_as_list, key=lambda k: k['timestamp']) 
        return tasks_as_list_sorted

    def tasks_for_day(self, day):
        tasks = self.db \
                    .child(self.username) \
                    .child(self.tasks_database) \
                    .child(day) \
                    .get(self.db_connection.get_token()) \
                    .val()
        if tasks:
            return self.tasks_to_list(tasks)
        return []

    def get_all_tasks(self):
        whole_db = self.db \
                       .child(self.username) \
                       .child('tasks') \
                       .get(self.db_connection.get_token()).val()
        tasks = []
        for date in whole_db:
            for task in whole_db[date]:
                tasks.append(whole_db[date][task])
        return tasks

    def get_user_settings(self, key=None):
        if key is None:
            settings = self.db \
                           .child(self.username) \
                           .child('settings') \
                           .get(self.db_connection.get_token()) \
                           .val()
            return settings
        else:
            setting = self.db \
                          .child(self.username) \
                          .child('settings') \
                          .child(key) \
                          .get(self.db_connection.get_token()) \
                          .val()
            return setting

    @staticmethod
    def settings_are_valid(key, value):
        if key in DATA_SETTINGS:
            return True # Accept any values for these
        if key not in ALL_USER_SETTINGS_OPTIONS:
            return False
        if value not in ALL_USER_SETTINGS_OPTIONS[key]:
            return False
        return True


    def set_user_setting(self, key, value):
        if self.settings_are_valid(key, value):
            self.db \
                .child(self.username) \
                .child('settings') \
                .child(key) \
                .set(value, self.db_connection.get_token())
            return
        raise SettingsError("'{}' cannot be set to '{}'.".format(key, value))

    def test_database(self, fix_errors=False):
        whole_db = self.db \
                       .child(self.username) \
                       .child('tasks') \
                       .get(self.db_connection.get_token()).val()
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

    def __init__(self, username, task_db, date_due, task_key=None, description=None):
        self.tasks_database = UserTasks(username, task_db)
        if task_key:
            self.date_due = date_due
            self.task_key = task_key
        elif description:
            self.date_due, self.task_key = self.tasks_database.insert_task(description, date_due)
        elif not task_key and not description:
            raise TaskError('Must provide either task_key to retrieve task, or description to create task')

    def __str__(self):
        desc = self.details()['description']
        return '{} {}: {}'.format(self.date_due, self.task_key, desc)

    def details(self):
        key, task_data = self.tasks_database.get_task(self.date_due, self.task_key)
        task_data['task_key'] = key
        return task_data

    def delete(self):
        self.tasks_database.delete_task(self.date_due, self.task_key)

    def update(self, update_data):
        result = self.tasks_database.update_task(self.date_due, self.task_key, update_data)
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


