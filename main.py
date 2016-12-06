from snoohelper.webapp.webapp import app

if __name__ == '__main__':
    context = ('santihub.crt', 'santihub.key')
    app.run(host='0.0.0.0', port=5023, ssl_context=context, threaded=True)
