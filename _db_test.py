import pymysql
from app.core.config import settings

def tc(host):
    try:
        c = pymysql.connect(
            host=host,
            user=settings.db_user,
            password=(settings.db_password or None),
            port=settings.db_port,
            connect_timeout=3,
        )
        c.close()
        print('OK', host)
    except Exception as e:
        print('FAIL', host, type(e).__name__, e)

tc(settings.db_host)
tc('127.0.0.1')
tc('localhost')
