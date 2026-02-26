from typing import List, Optional
from dataclasses import dataclass
import sqlite3
from sqlite3 import Connection
import os

from datetime import datetime


@dataclass
class Task:
    id: Optional[int]
    name: str
    description: str
    priority: int  # enum type
    created_at: Optional[
        str
    ]  # we handle dates on the frontend, no date should be kept visible here because it literally doesnt matter
    due_date: Optional[str]
    is_complete: Optional[bool] = False
    is_hidden: Optional[bool] = False
    meta_data: Optional[str] = "{}"


class TaskDB:
    def __init__(self, db_name="task_board.db"):
        self.db_name = db_name
        self._init_db()  # fix: ensure table exists on construction

    def _get_connection(self):
        conn: Connection = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # create the table
            conn.execute(
                f"""
                create table if not exists tasks ( -- master table, all tasks live here
                    id integer primary key autoincrement,
                    name text not null,
                    description text not null,
                    priority integer not null,
                    created_at text not null default current_timestamp,  -- fix: removed invalid 'date' type keyword
                    due_date date not null default 0, -- This makes it easy to filter for tasks without a duedate
                    is_complete integer not null default 0,
                    is_hidden integer not null default 0,
                    meta_data text -- just in case we need to do some cursed shit? 
                )"""
            )

    def _create_tasks_list(self, rows) -> List[Task]:
        tasks = []
        for row in rows:
            tasks.append(
                Task(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    priority=row["priority"],
                    created_at=row["created_at"],
                    due_date=row["due_date"],
                    is_complete=bool(row["is_complete"]),
                    is_hidden=bool(row["is_hidden"]),
                    meta_data=row["meta_data"],
                )
            )
        return tasks

    def add_task(self, task: Task) -> None:
        with self._get_connection() as conn:
            query = "insert into tasks(name, description, priority, created_at, due_date, is_complete, is_hidden, meta_data) values (?, ?, ?, ?, ?, ?, ?, ?)"
            # fix: fallback to now() so we never insert NULL over the SQL DEFAULT
            created = task.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = (
                task.name,
                task.description,
                task.priority,
                created,
                task.due_date,
                int(task.is_complete),
                int(task.is_hidden),
                task.meta_data,
            )
            conn.execute(query, data)

    def edit_task(self, task_id: int, **fields):
        if "id" in fields:
            fields.pop("id")

        if not fields:
            return

        columns = ",".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values())
        values.append(task_id)

        with self._get_connection() as conn:
            query = f"UPDATE tasks SET {columns} WHERE id = ?"
            conn.execute(query, values)

    def remove_task(self, task_id: int):
        """This doesnt remove a task it just hides it from view,
        just in case you accidentally delete a task or need it later."""

        with self._get_connection() as conn:
            conn.execute("update tasks SET is_hidden = 1 where id = ?", (task_id,))

    def get_all_incomplete_tasks(self):
        with self._get_connection() as conn:
            cursor = conn.execute(
                "select * from tasks where is_hidden = 0 and is_complete = 0"
            )
            rows = cursor.fetchall()
            return self._create_tasks_list(rows)

    def get_all_complete_tasks(self):
        with self._get_connection() as conn:
            cursor = conn.execute(
                "select * from tasks where is_hidden = 0 and is_complete = 1"
            )
            rows = cursor.fetchall()
            return self._create_tasks_list(rows)

    def get_all_undue_tasks(self):
        with self._get_connection() as conn:
            cur = conn.execute("select * from tasks where due_date = 0")
            rows = cur.fetchall()
            return self._create_tasks_list(rows)

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        with self._get_connection() as conn:
            cur = conn.execute("select * from tasks where id = ?", (task_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._create_tasks_list([row])[0]

    def get_days_until_due(self, task_id):
        with self._get_connection() as conn:

            cursor = conn.execute(
                """
                select id, name, julianday(due_date) - julianday('now') as diff_days
                from tasks where id = ?  -- fix: was julianday(created_at), should be 'now'
                """,
                (task_id,),
            )
            rows = cursor.fetchall()
            return self._create_tasks_list(rows)


# small test
if __name__ == "__main__":
    test_db = "test_task_board.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    database = TaskDB(db_name=test_db)
    database._init_db()
    # Our first write
    database.add_task(
        Task(
            id=None,
            name="Hello! This is a test task",
            description="This is a test description",
            priority=0,
            is_complete=False,
            is_hidden=0,
            meta_data="""{"meta-Data" : "this is a test"}""",
        )
    )
    # validate it
    print(
        f"Completed Tasks: {database.get_all_complete_tasks()}\n",
        f"Incompleted Tasks: {database.get_all_incomplete_tasks()}\n",
    )  # should be 1, theres on task and its incomplete

    # we need to add more varying data
    database.add_task(
        Task(
            id=None,
            name="Hello! This is a complete task",
            description="This is a complete description",
            priority=1,  # invalid priority, shouldnt ever happen in prod.
            is_complete=True,  # an example of a complete task
            is_hidden=1,  # does it really hide our data?
            meta_data="""{"meta-Data" : "this is a complete test!"}""",
        )
    )

    # validate it
    print(
        f"Completed Tasks: {database.get_all_complete_tasks()}\n",
        f"Incompleted Tasks: {database.get_all_incomplete_tasks()}\n",
    )

    database.add_task(
        Task(
            id=None,
            name="Hello! This is a third task",
            description="This is a third description",
            priority=3,
            is_complete=False,
            is_hidden=0,
            meta_data="""{"meta-Data" : "this is a test"}""",
        )
    )

    # validate it
    print(
        f"Completed Tasks: {database.get_all_complete_tasks()}\n",
        f"Incompleted Tasks: {database.get_all_incomplete_tasks()}\n",
    )

    print(
        "Add task test suite\n",
        "getting completed tasks: ",
        len(
            database.get_all_complete_tasks()
        ),  # should be 0, task (2) is complete but is_hidden=1 so it won't show
        "\ngetting incomplete tasks: ",
        len(
            database.get_all_incomplete_tasks()
        ),  # Should be 2, theres two incomplete tasks (1, 3)
    )

    print(database.get_all_complete_tasks())

    # lets edit the first task and mark it as complete

    database.edit_task(task_id=1, is_complete=True)
    print(
        database.get_all_incomplete_tasks()
    )  # should be 1, theres on task and its incomplete

    print(
        "Edit task test suite\n",
        "getting completed tasks: ",
        len(
            database.get_all_complete_tasks()
        ),  # this should be 1 now, task 1 is complete & visible; task 2 is still hidden
        "\ngetting incomplete tasks: ",
        len(
            database.get_all_incomplete_tasks()
        ),  # this should be 1 since task 1 no longer is incomplete
    )

    # lets remove the second task
    database.remove_task(task_id=2)  # this task (2) is now deleted

    print(
        "remove task test suite",
        "getting completed tasks: ",
        len(database.get_all_complete_tasks()),  # this should be 1
        "\ngetting incomplete tasks: ",
        len(database.get_all_incomplete_tasks()),  # this should be 1
    )
