from snoohelper.webapp.webapp import create_app
from snoohelper.utils.teams import SlackTeamsController
from snoohelper.webapp.requests_handler import RequestsHandler

if __name__ == '__main__':
    context = ('santihub.crt', 'santihub.key')
    controller = SlackTeamsController("teams.ini", 'snoohelper_master.db')
    handler = RequestsHandler(controller)
    app = create_app(controller, handler)
    app.run(host='0.0.0.0', port=5023, ssl_context=context, threaded=True)
