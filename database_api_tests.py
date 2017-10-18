
import unittest
import random, time
from tasklist import TaskDB, UserTasks, TaskError

db_connection = TaskDB()

class UserTasksTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.test_task_db = UserTasks('test_tanuki', db_connection)
        self.day = '20170218'
        self.tomorrow = '20170219'

    @classmethod
    def tearDownClass(self):
        self.test_task_db.delete_all_tasks_for_date(self.day)
        self.test_task_db.delete_all_tasks_for_date(self.tomorrow)

    def random_task(self):
        random_alphabet = 'abcd efghijk lmno pqrs tuvwx yzAB CDEFGHIJ KLMNOP QRSTU VWXYZ '
        return 'random task {}'.format(''.join(random.choice(random_alphabet) for x in range(20)))

    def test_insert_task(self):
        task = self.random_task()
        test_date, test_key = self.test_task_db.insert_task(task, self.day)
        read_key, read_obj = self.test_task_db.get_task(test_date, test_key)
        self.assertEquals(read_key, test_key)
        self.assertEquals(read_obj['description'], task)

    def test_delete_task(self):
        task = self.random_task()
        test_date, test_key = self.test_task_db.insert_task(task, self.day)
        expected_error = 'Task {} {} could not be retrieved.'.format(self.day, test_key)
        self.test_task_db.delete_task(self.day, test_key)
        with self.assertRaises(TaskError) as taskerror:
            read_key, read_obj = self.test_task_db.get_task(test_date, test_key)
        self.assertEquals(str(taskerror.exception), expected_error)

    def test_update_task(self):
        task = self.random_task()
        test_date, test_key = self.test_task_db.insert_task(task, self.day)
        new_description = self.random_task()
        self.test_task_db.update_task(self.day, test_key, {'description': new_description})
        read_key, read_obj = self.test_task_db.get_task(self.day, test_key)
        self.assertEquals(read_obj['description'], new_description)

    def test_timestamp_updated(self):
        task = self.random_task()
        test_date, test_key = self.test_task_db.insert_task(task, self.day)
        timestamp = self.test_task_db.get_last_updated_time(self.day)
        time.sleep(1)
        self.test_task_db.update_task(self.day, test_key, {'description': self.random_task()})
        self.assertNotEqual(timestamp, self.test_task_db.get_last_updated_time(self.day))

    def test_update_task_with_new_date_moved_to_new_day(self):
        task = self.random_task()
        test_date, test_key = self.test_task_db.insert_task(task, self.day)
        new_date, new_key = self.test_task_db.update_task(self.day, test_key, {'date_or_project': self.tomorrow})
        read_key, read_obj = self.test_task_db.get_task(self.tomorrow, new_key)
        self.assertEquals(read_obj['description'], task)

    def test_update_task_with_new_date_removed_from_old_day(self):
        task = self.random_task()
        test_date, test_key = self.test_task_db.insert_task(task, self.day)
        expected_error = 'Task {} {} could not be retrieved.'.format(self.day, test_key)
        new_date, new_key = self.test_task_db.update_task(self.day, test_key, {'date_or_project': self.tomorrow})
        with self.assertRaises(TaskError) as taskerror:
            read_key, read_obj = self.test_task_db.get_task(self.day, test_key)
        self.assertEquals(str(taskerror.exception), expected_error)

    def test_tasks_for_day(self):
        test_keys = []
        tasks = [self.random_task() for x in range(5)]
        for t in tasks:
            date, key = self.test_task_db.insert_task(t, self.day)
            test_keys.append(key)
        for i in range(5):
            key, obj = self.test_task_db.get_task(self.day, test_keys[i])
            self.assertEquals(obj['description'], tasks[i])

if __name__ == "__main__":
    unittest.main()
