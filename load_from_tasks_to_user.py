from tasklist import TaskDB
db = TaskDB()

username = 'heytanuki@gmailcom'

my_data = db.database.child('tasks').get(db.get_token()).val()

for item in my_data:
    db.database.child(username).child('tasks').child(item).set(my_data[item], db.get_token())