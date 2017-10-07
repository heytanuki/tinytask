import flask
from conf.secrets import APP_SECRET_KEY

app = flask.Flask(__name__)
app.secret_key = APP_SECRET_KEY_PROD
task_db = TaskDB()

##########
# Routes #
##########

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    username = flask.session.get('tinytask_username', None)
    if username:
        flask.session['tinytask_username'] = None
    content = """
        has moved to <a href="http://tinytask.space" class="underlined">tinytask.space</a>!
        <p>If you have bookmarks or home screen shortcuts, remove them, go to the new domain, log in, and add them again.</p>
        """
    return flask.render_template('index.html', content=content)

if __name__ == '__main__':
    app.secret_key = APP_SECRET_KEY
    app.run(host='0.0.0.0', port=8080, debug=True)

