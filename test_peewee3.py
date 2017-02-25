import sys
import unittest

from peewee3 import *


def __sql__(q):
    return Context().sql(q).query()


User = Table('users')
Tweet = Table('tweets')


class BaseTestCase(unittest.TestCase):
    pass


class TestSimpleJoin(BaseTestCase):
    def test_simple_join(self):
        query = (User
                 .select(
                     User.c.id,
                     User.c.username,
                     fn.COUNT(Tweet.c.id).alias('ct'))
                 .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                 .group_by(User.c.id, User.c.username))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."username", COUNT("t2"."id") AS ct '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweets" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id", "t1"."username"'))
        self.assertEqual(params, [])


class TestSubquery(BaseTestCase):
    def test_subquery(self):
        inner = (Tweet
                 .select(fn.COUNT(Tweet.c.id).alias('ct'))
                 .where(Tweet.c.user == User.c.id))
        query = (User
                 .select(User.c.username, inner.alias('iq'))
                 .order_by(User.c.username))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."username", '
            '(SELECT COUNT("t2"."id") AS ct '
            'FROM "tweets" AS "t2" '
            'WHERE ("t2"."user" = "t1"."id")) AS "iq" '
            'FROM "users" AS "t1" ORDER BY "t1"."username"'))
        self.assertEqual(params, [])


class TestUserDefinedAlias(BaseTestCase):
    def test_user_defined_alias(self):
        UA = User.alias('alt')
        query = (User
                 .select(User.c.id, User.c.username, UA.c.nuggz)
                 .join(UA, on=(User.c.id == UA.c.id))
                 .order_by(UA.c.nuggz))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."username", "alt"."nuggz" '
            'FROM "users" AS "t1" '
            'INNER JOIN "users" AS "alt" ON ("t1"."id" = "alt"."id") '
            'ORDER BY "alt"."nuggz"'))


class TestComplexSelect(BaseTestCase):
    def test_complex_select(self):
        Order = Table('orders', columns=(
            'region',
            'amount',
            'product',
            'quantity'))

        regional_sales = (Order
                          .select(
                              Order.region,
                              fn.SUM(Order.amount).alias('total_sales'))
                          .group_by(Order.region)
                          .cte('regional_sales'))

        top_regions = (regional_sales
                       .select(regional_sales.c.region)
                       .where(regional_sales.c.total_sales > (
                           regional_sales.select(
                               fn.SUM(regional_sales.c.total_sales) / 10)))
                       .cte('top_regions'))

        query = (Order
                 .select(
                     Order.region,
                     Order.product,
                     fn.SUM(Order.quantity).alias('product_units'),
                     fn.SUM(Order.amount).alias('product_sales'))
                 .where(
                     Order.region << top_regions.select(top_regions.c.region))
                 .group_by(Order.region, Order.product)
                 .with_cte(regional_sales, top_regions))

        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'WITH "regional_sales" AS ('
            'SELECT "a1"."region", SUM("a1"."amount") AS total_sales '
            'FROM "orders" AS "a1" '
            'GROUP BY "a1"."region"'
            '), '
            '"top_regions" AS ('
            'SELECT "regional_sales"."region" '
            'FROM "regional_sales" '
            'WHERE ("regional_sales"."total_sales" > '
            '(SELECT (SUM("regional_sales"."total_sales") / ?) '
            'FROM "regional_sales"))'
            ') '
            'SELECT "t1"."region", "t1"."product", '
            'SUM("t1"."quantity") AS product_units, '
            'SUM("t1"."amount") AS product_sales '
            'FROM "orders" AS "t1" '
            'WHERE ('
            '"t1"."region" IN ('
            'SELECT "top_regions"."region" '
            'FROM "top_regions")'
            ') GROUP BY "t1"."region", "t1"."product"'))
        self.assertEqual(params, [10])


class TestCompoundSelect(BaseTestCase):
    def test_compound_select(self):
        lhs = User.select(User.c.id).where(User.c.username == 'charlie')
        rhs = User.select(User.c.username).where(User.c.admin == True)
        q2 = (lhs | rhs)
        UA = User.alias('U2')
        q3 = q2 | UA.select(UA.c.id).where(UA.c.superuser == False)

        sql, params = __sql__(q3)
        self.assertEqual(sql, (
            'SELECT "t1"."id" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?) '
            'UNION '
            'SELECT "a1"."username" '
            'FROM "users" AS "a1" '
            'WHERE ("a1"."admin" = ?) '
            'UNION '
            'SELECT "U2"."id" '
            'FROM "users" AS "U2" '
            'WHERE ("U2"."superuser" = ?)'))
        self.assertEqual(params, ['charlie', True, False])


class TestInsertQuery(BaseTestCase):
    def test_insert_query(self):
        query = User.insert({
            User.c.username: 'charlie',
            User.c.superuser: False,
            User.c.admin: True})
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("admin", "superuser", "username") '
            'VALUES (?, ?, ?)'))
        self.assertEqual(params, [True, False, 'charlie'])


class TestUpdateQuery(BaseTestCase):
    def test_update_query(self):
        query = (User
                 .update({
                     User.c.username: 'nuggie',
                     User.c.admin: False,
                     User.c.counter: User.c.counter + 1})
                 .where(User.c.username == 'nugz'))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'UPDATE "users" SET '
            '"admin" = ?, '
            '"counter" = ("counter" + ?), '
            '"username" = ? '
            'WHERE ("username" = ?)'))
        self.assertEqual(params, [False, 1, 'nuggie', 'nugz'])

    def test_update_subquery(self):
        subquery = (User
                    .select(User.c.id, fn.COUNT(Tweet.c.id).alias('ct'))
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(SQL('ct') > 100))
        query = (User
                 .update({
                     User.c.muted: True,
                     User.c.counter: 0})
                 .where(User.c.id << subquery))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'UPDATE "users" SET '
            '"counter" = ?, '
            '"muted" = ? '
            'WHERE ("id" IN ('
            'SELECT "t1"."id", COUNT("t2"."id") AS ct '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweets" AS "t2" '
            'ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id" '
            'HAVING (ct > ?)))'))
        self.assertEqual(params, [0, True, 100])


class TestDeleteQuery(BaseTestCase):
    def test_delete_query(self):
        query = (User
                 .delete()
                 .where(User.c.username != 'charlie')
                 .limit(3))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'DELETE FROM "users" WHERE ("username" != ?) LIMIT 3'))
        self.assertEqual(params, ['charlie'])

    def test_delete_subquery(self):
        subquery = (User
                    .select(User.c.id, fn.COUNT(Tweet.c.id).alias('ct'))
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(SQL('ct') > 100))
        query = (User
                 .delete()
                 .where(User.c.id << subquery))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'DELETE FROM "users" '
            'WHERE ("id" IN ('
            'SELECT "t1"."id", COUNT("t2"."id") AS ct '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweets" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id" '
            'HAVING (ct > ?)))'))
        self.assertEqual(params, [100])


class QueryCountSqliteDatabase(SqliteDatabase):
    def __init__(self, *a, **k):
        super(QueryCountSqliteDatabase, self).__init__(*a, **k)
        self.count = 0

    def execute_sql(self, sql, *args):
        self.count += 1
        return super(QueryCountSqliteDatabase, self).execute_sql(sql, *args)


db = QueryCountSqliteDatabase(':memory:')


class TestModel(Model):
    class Meta:
        database = db

class Person(TestModel):
    first = CharField()
    last = CharField()
    dob = DateField(index=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )

class Note(TestModel):
    author = ForeignKeyField(Person)
    content = TextField()

class Category(TestModel):
    parent = ForeignKeyField('self', backref='children', null=True)
    name = CharField(max_length=20, primary_key=True)


class TestModelSQL(BaseTestCase):
    def assertCreateTable(self, model_class, expected):
        sql, params = model_class._schema._create_table(False).query()
        self.assertEqual(params, [])

        indexes = []
        for create_index in model_class._schema._create_indexes(False):
            isql, params = create_index.query()
            self.assertEqual(params, [])
            indexes.append(isql)

        self.assertEqual([sql] + indexes, expected)

    def test_table_and_index_creation(self):
        self.assertCreateTable(Person, [
            ('CREATE TABLE "person" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"first" VARCHAR(255) NOT NULL, '
             '"last" VARCHAR(255) NOT NULL, '
             '"dob" DATE NOT NULL)'),
            'CREATE INDEX "person_dob" ON "person" ("dob")',
            ('CREATE UNIQUE INDEX "person_first_last" ON '
             '"person" ("first", "last")'),
        ])

        self.assertCreateTable(Note, [
            ('CREATE TABLE "note" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"author_id" INTEGER NOT NULL, '
             '"content" TEXT NOT NULL, '
             'FOREIGN KEY ("author_id") REFERENCES "person" ("id"))'),
            'CREATE INDEX "note_author" ON "note" ("author_id")',
        ])

        self.assertCreateTable(Category, [
            ('CREATE TABLE "category" ('
             '"name" VARCHAR(20) NOT NULL PRIMARY KEY, '
             '"parent_id" VARCHAR(20), '
             'FOREIGN KEY ("parent_id") REFERENCES "category" ("name"))'),
            'CREATE INDEX "category_parent" ON "category" ("parent_id")',
        ])

    def test_select(self):
        query = (Person
                 .select(
                     Person.first,
                     Person.last,
                     fn.COUNT(Note.id).alias('ct'))
                 .join(Note)
                 .where((Person.last == 'Leifer') & (Person.id < 4)))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."first", "t1"."last", COUNT("t2"."id") AS ct '
            'FROM "person" AS "t1" '
            'INNER JOIN "note" AS "t2" ON ("t2"."author_id" = "t1"."id") '
            'WHERE ('
            '("t1"."last" = ?) AND '
            '("t1"."id" < ?))'))
        self.assertEqual(params, ['Leifer', 4])

    def test_insert(self):
        query = (Person
                 .insert({Person.first: 'huey',
                          Person.last: 'cat',
                          Person.dob: datetime.date(2011, 1, 1)}))
        sql, params = __sql__(query)
        self.assertEqual(sql, ('INSERT INTO "person" ("first", "last", "dob") '
                               'VALUES (?, ?, ?)'))
        self.assertEqual(params, ['huey', 'cat', datetime.date(2011, 1, 1)])

        query = (Note
                 .insert({Note.author: Person(id=1337),
                          Note.content: 'leet'}))
        sql, params = __sql__(query)
        self.assertEqual(sql, ('INSERT INTO "note" ("author_id", "content") '
                               'VALUES (?, ?)'))
        self.assertEqual(params, [1337, 'leet'])

    def test_insert_many(self):
        query = (Note
                 .insert_many((
                     {Note.author: Person(id=1), Note.content: 'note-1'},
                     {Note.author: Person(id=2), Note.content: 'note-2'},
                     {Note.author: Person(id=3), Note.content: 'note-3'})))
        sql, params = __sql__(query)
        self.assertEqual(sql, ('INSERT INTO "note" ("author_id", "content") '
                               'VALUES (?, ?), (?, ?), (?, ?)'))
        self.assertEqual(params, [1, 'note-1', 2, 'note-2', 3, 'note-3'])

    def test_insert_query(self):
        select = (Person
                  .select(Person.id, Person.first)
                  .where(Person.last == 'cat'))
        query = Note.insert_from(select, (Note.author, Note.content))
        sql, params = __sql__(query)
        self.assertEqual(sql, ('INSERT INTO "note" ("author_id", "content") '
                               'SELECT "t1"."id", "t1"."first" '
                               'FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)'))
        self.assertEqual(params, ['cat'])

    def test_update(self):
        class Stat(TestModel):
            url = TextField()
            count = IntegerField()
            timestamp = TimestampField()

        query = (Stat
                 .update({Stat.count: Stat.count + 1,
                          Stat.timestamp: datetime.datetime(2017, 1, 1)})
                 .where(Stat.url == '/peewee'))
        sql, params = __sql__(query)
        self.assertEqual(sql, ('UPDATE "stat" SET "count" = ("count" + ?), '
                               '"timestamp" = ? WHERE ("url" = ?)'))
        self.assertEqual(params, [1, datetime.datetime(2017, 1, 1), '/peewee'])

    def test_delete(self):
        query = (Note
                 .delete()
                 .where(Note.author << (Person.select(Person.id)
                                        .where(Person.last == 'cat'))))
        sql, params = __sql__(query)
        self.assertEqual(sql, ('DELETE FROM "note" '
                               'WHERE ("author_id" IN ('
                               'SELECT "t1"."id" FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)))'))
        self.assertEqual(params, ['cat'])

        query = Note.delete().where(Note.author == Person(id=123))
        sql, params = __sql__(query)
        self.assertEqual(sql, 'DELETE FROM "note" WHERE ("author_id" = ?)')
        self.assertEqual(params, [123])


class TestModelAPIs(BaseTestCase):
    def setUp(self):
        super(TestModelAPIs, self).setUp()
        Person._schema.create_table()
        Note._schema.create_table()

    def tearDown(self):
        super(TestModelAPIs, self).tearDown()
        db.close()

    def add_person(self, first, last):
        return Person.create(first=first, last=last,
                             dob=datetime.date(2000, 1, 1))

    def add_notes(self, person, *notes):
        for note in notes:
            Note.create(author=person, content=note)

    @contextmanager
    def assertQueryCount(self, n):
        curr = db.count
        yield
        self.assertEqual(db.count - curr, n)

    def test_create(self):
        with self.assertQueryCount(1):
            huey = self.add_person('huey', 'cat')
            self.assertEqual(huey.first, 'huey')
            self.assertEqual(huey.last, 'cat')
            self.assertEqual(huey.id, 1)

        with self.assertQueryCount(1):
            note = Note.create(author=huey, content='meow')
            self.assertEqual(note.author.id, huey.id)
            self.assertEqual(note.author.first, 'huey')
            self.assertEqual(note.content, 'meow')
            self.assertEqual(note.id, 1)

    def test_model_select(self):
        query = (Note
                 .select(Note.content, Person.first, Person.last)
                 .join(Person)
                 .order_by(Person.first, Note.content))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."content", "t2"."first", "t2"."last" '
            'FROM "note" AS "t1" '
            'INNER JOIN "person" AS "t2" '
            'ON ("t1"."author_id" = "t2"."id") '
            'ORDER BY "t2"."first", "t1"."content"'))
        self.assertEqual(params, [])

        huey = self.add_person('huey', 'cat')
        mickey = self.add_person('mickey', 'dog')
        zaizee = self.add_person('zaizee', 'cat')

        self.add_notes(huey, 'meow', 'hiss', 'purr')
        self.add_notes(mickey, 'woof', 'whine')

        with self.assertQueryCount(1):
            notes = list(query)
            self.assertEqual([(n.content, n.author.first, n.author.last)
                              for n in notes], [
                                  ('hiss', 'huey', 'cat'),
                                  ('meow', 'huey', 'cat'),
                                  ('purr', 'huey', 'cat'),
                                  ('whine', 'mickey', 'dog'),
                                  ('woof', 'mickey', 'dog')])


if __name__ == '__main__':
    unittest.main(argv=sys.argv)