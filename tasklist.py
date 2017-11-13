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
        print '*** Initialized!'

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
        print '*** Reconnecting...'
        try:
            self.user = self.auth.refresh(self.user['refreshToken'])
            expiration_timedelta = datetime.timedelta(seconds=int(self.user['expiresIn']) - 600) # trigger refresh 10 minutes early
            self.expiry_time = datetime.datetime.now() + expiration_timedelta
            print '*** Reconnected!'
        except KeyError:
            print '*** Error reconnecting, re-initializing...'
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
                     .child(data['date_or_project']) \
                     .push(data, self.db_connection.get_token())
        self.set_last_updated_time(data['date_or_project'])
        return result

    def insert_task(self, description, date_or_project=None):
        if not date_or_project:
            raise TaskError('Task was submitted without a date or project.')
        data = {
            'description': description,
            'date_or_project': date_or_project,
            'status': 'notdone',
        }
        result = self.insert_data(data)
        return (date_or_project, result['name'])

    def set_last_updated_time(self, date_or_project):
        if not date_or_project:
            raise TaskError('Tried to update time for invalid date or project.')
        update_time = int(time.time())
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_or_project) \
            .child('last_updated') \
            .set(update_time, self.db_connection.get_token())
        return update_time

    def get_last_updated_time(self, date_or_project):
        updated_time = self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_or_project) \
            .child('last_updated') \
            .get(self.db_connection.get_token()) \
            .val()
        if updated_time is None:
            return 0
        return updated_time

    def get_task(self, date_or_project, task_key):
        try:
            task = self.db \
                       .child(self.username) \
                       .child(self.tasks_database) \
                       .child(date_or_project) \
                       .order_by_child('$key') \
                       .equal_to(str(task_key)) \
                       .get(self.db_connection.get_token()) \
                       .val()
        except IndexError:
            raise TaskError('Task {} {} could not be retrieved.'.format(date_or_project, task_key))
        for key in task:
            return (key, task[key])

    def update_task(self, date_or_project, task_key, update_data):
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_or_project) \
            .child(task_key) \
            .update(update_data, self.db_connection.get_token())
        self.set_last_updated_time(date_or_project)
        if 'date_or_project' in update_data:
            if update_data['date_or_project'] != date_or_project:
                old_key, task_data = self.get_task(date_or_project, task_key)
                result = self.insert_data(task_data)
                new_key = result['name']
                self.delete_task(date_or_project, task_key)
                return (update_data['date_or_project'], new_key)

    def delete_task(self, date_or_project, task_key):
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_or_project) \
            .child(task_key) \
            .remove(self.db_connection.get_token())
        self.set_last_updated_time(date_or_project)

    def delete_all_tasks_for_date(self, date_or_project):
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_or_project) \
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

    def get_task_group(self, date_or_project):
        tasks = self.db \
                    .child(self.username) \
                    .child(self.tasks_database) \
                    .child(date_or_project) \
                    .get(self.db_connection.get_token()) \
                    .val()
        if tasks:
            return self.tasks_to_list(tasks)
        return []

    def get_all_dates_or_projects(self):
        task_group = self.db \
                         .child(self.username) \
                         .child(self.tasks_database) \
                         .get(self.db_connection.get_token()).val()
        if task_group:
            all_tasks_in_group = [p for p in task_group]
            return all_tasks_in_group
        else:
            return []

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

    def archive_group(self, date_or_project):
        tasks = self.get_task_group(date_or_project)
        for task in tasks:
            self.move_task_to_archive(task)
        self.delete_group(date_or_project)

    def move_task_to_archive(self, task_dict):
        task_key = task_dict.pop('task_key')
        self.db \
            .child(self.username) \
            .child('archive') \
            .push(task_dict, self.db_connection.get_token())
        self.delete_task(task_dict['date_or_project'], task_key)

    def delete_group(self, date_or_project):
        tasks = self.get_task_group(date_or_project)
        if len(tasks) > 0:
            raise TaskError('Cannot delete group {}: it has tasks still in it.'.format(date_or_project))
        self.db \
            .child(self.username) \
            .child(self.tasks_database) \
            .child(date_or_project) \
            .remove(self.db_connection.get_token())

    def get_archive(self):
        archive = self.db \
                      .child(self.username) \
                      .child('archive') \
                      .get(self.db_connection.get_token()) \
                      .val()
        return archive


class TaskItem(object):

    def __init__(self, user_tasks_db, date_or_project, task_key=None, description=None):
        self.tasks_database = user_tasks_db
        if task_key:
            self.date_or_project = date_or_project
            self.task_key = task_key
        elif description:
            self.date_or_project, self.task_key = self.tasks_database.insert_task(description, date_or_project)
        elif not task_key and not description:
            raise TaskError('Must provide either task_key to retrieve task, or description to create task')

    def __str__(self):
        desc = self.details()['description']
        return '{} {}: {}'.format(self.date_or_project, self.task_key, desc)

    def details(self):
        key, task_data = self.tasks_database.get_task(self.date_or_project, self.task_key)
        task_data['task_key'] = key
        return task_data

    def delete(self):
        self.tasks_database.delete_task(self.date_or_project, self.task_key)

    def update(self, update_data):
        result = self.tasks_database.update_task(self.date_or_project, self.task_key, update_data)
        if result:
            self.date_or_project, self.task_key = result

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







