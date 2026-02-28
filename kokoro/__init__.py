import gevent.monkey

gevent.monkey.patch_all()

from psycogreen.gevent import patch_psycopg

patch_psycopg()
