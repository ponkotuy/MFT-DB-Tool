from flask import Flask

from constant import DATABASE_PATH
from service.i_database_service import IDataBaseService
from service.lens_service import LensService
from service.sqlite_database_service import SqliteDataBaseService

app = Flask(__name__)
database: IDataBaseService = SqliteDataBaseService(DATABASE_PATH)
lens_service = LensService(database)


@app.route('/')
def hello():
    return 'hello, world'


if __name__ == '__main__':
    app.run(debug=True)
