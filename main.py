from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    Rule,
    Select,
    Static,
    TextArea,
)

from modules.database import Task, TaskDB

# ── priority helpers ──────────────────────────────────────────────────────────

PRIORITY_LABELS = {0: "Low", 1: "Medium", 2: "High", 3: "Critical"}
PRIORITY_SHORT = {0: "○ L", 1: "◑ M", 2: "● H", 3: "◉ C"}
PRIORITY_COLORS = {0: "green", 1: "yellow", 2: "#fab387", 3: "red"}


def _due_markup(due_date: str) -> str:
    """Short due-date string with Rich markup for the table cell."""
    if not due_date or due_date == "0":
        return "[dim]–[/dim]"
    try:
        dt = datetime.strptime(due_date, "%Y-%m-%d")
        diff = (dt.date() - datetime.today().date()).days
        if diff < 0:
            return f"[red]Overdue ({abs(diff)}d)[/red]"
        if diff == 0:
            return "[yellow]Today[/yellow]"
        if diff == 1:
            return "[yellow]Tomorrow[/yellow]"
        return f"{dt.strftime('%b %d')} ({diff}d)"
    except ValueError:
        return due_date


def _due_plain(due_date: str) -> str:
    """Human-readable due-date string without markup for the detail panel."""
    if not due_date or due_date == "0":
        return "No due date"
    try:
        dt = datetime.strptime(due_date, "%Y-%m-%d")
        diff = (dt.date() - datetime.today().date()).days
        if diff < 0:
            return f"Overdue by {abs(diff)} day(s)"
        if diff == 0:
            return "Due today"
        if diff == 1:
            return "Due tomorrow"
        return f"{dt.strftime('%b %d, %Y')}  (+{diff}d)"
    except ValueError:
        return due_date


# ── modals ────────────────────────────────────────────────────────────────────


class AddEditTaskModal(ModalScreen):
    """Add or edit a task."""

    def __init__(self, task: Optional[Task] = None, **kwargs):
        super().__init__(**kwargs)
        self._task_data = task

    def compose(self) -> ComposeResult:
        is_edit = self._task_data is not None
        with Container(id="modal-container"):
            yield Label("Edit Task" if is_edit else "New Task", id="modal-title")
            yield Rule()

            yield Label("Name", classes="field-label")
            yield Input(
                value=self._task_data.name if is_edit else "",
                placeholder="Task name…",
                id="task-name",
            )

            yield Label("Description", classes="field-label")
            yield TextArea(
                text=self._task_data.description if is_edit else "",
                id="task-description",
            )

            yield Label("Priority", classes="field-label")
            yield Select(
                options=[("Low", 0), ("Medium", 1), ("High", 2), ("Critical", 3)],
                value=self._task_data.priority if is_edit else 1,
                id="task-priority",
                allow_blank=False,
            )

            yield Label("Due Date  (YYYY-MM-DD, blank = none)", classes="field-label")
            current_due = (
                self._task_data.due_date
                if is_edit
                and self._task_data.due_date
                and self._task_data.due_date != "0"
                else ""
            )
            yield Input(
                value=current_due,
                placeholder="YYYY-MM-DD",
                id="task-due-date",
            )

            yield Rule()
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Save", variant="default", id="save-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            self._commit()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter" and not isinstance(self.focused, TextArea):
            self._commit()
        elif event.key in ("left", "right") and isinstance(self.focused, Button):
            self.focus_previous() if event.key == "left" else self.focus_next()
            event.stop()

    def _commit(self) -> None:
        name = self.query_one("#task-name", Input).value.strip()
        description = self.query_one("#task-description", TextArea).text.strip()
        sel = self.query_one("#task-priority", Select)
        priority = int(sel.value) if sel.value is not Select.BLANK else 1
        due_raw = self.query_one("#task-due-date", Input).value.strip()

        if not name:
            self.notify("Task name cannot be empty.", severity="error")
            return
        if due_raw:
            try:
                datetime.strptime(due_raw, "%Y-%m-%d")
            except ValueError:
                self.notify("Due date must be YYYY-MM-DD.", severity="error")
                return

        self.dismiss(
            {
                "name": name,
                "description": description,
                "priority": priority,
                "due_date": due_raw or "0",
            }
        )


class ConfirmModal(ModalScreen):
    """Yes/no confirmation dialog."""

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-container"):
            yield Label(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", variant="default", id="no-btn")
                yield Button("Delete", variant="default", id="yes-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes-btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter":
            self.dismiss(True)
        elif event.key in ("left", "right") and isinstance(self.focused, Button):
            self.focus_previous() if event.key == "left" else self.focus_next()
            event.stop()


# ── detail panel ─────────────────────────────────────────────────────────────


class TaskDetailPanel(Static):
    """Right-side widget that displays the currently selected task."""

    def compose(self) -> ComposeResult:
        yield Label("[dim]Select a task to see details[/dim]", id="detail-title")
        yield Rule(id="detail-rule")
        yield Label("", id="detail-description")
        yield Label("", id="detail-meta-1")
        yield Label("", id="detail-meta-2")
        yield Label("", id="detail-meta-3")
        yield Label("", id="detail-status")

    def update_task(self, task: Optional[Task]) -> None:
        if task is None:
            self.query_one("#detail-title").update(
                "[dim]Select a task to see details[/dim]"
            )
            for wid in (
                "#detail-description",
                "#detail-meta-1",
                "#detail-meta-2",
                "#detail-meta-3",
                "#detail-status",
            ):
                self.query_one(wid).update("")
            return

        pc = PRIORITY_COLORS.get(task.priority, "white")
        plabel = PRIORITY_LABELS.get(task.priority, "?")

        self.query_one("#detail-title").update(f"[bold]{task.name}[/bold]")
        self.query_one("#detail-description").update(
            task.description or "[dim]No description.[/dim]"
        )
        self.query_one("#detail-meta-1").update(
            f"[dim]Priority  [/dim][{pc}]{plabel}[/{pc}]"
        )
        self.query_one("#detail-meta-2").update(
            f"[dim]Due       [/dim]{_due_plain(task.due_date)}"
        )
        self.query_one("#detail-meta-3").update(
            f"[dim]Created   [/dim]{task.created_at or 'Unknown'}"
        )
        if task.is_complete:
            self.query_one("#detail-status").update("[green]✓  Completed[/green]")
        else:
            self.query_one("#detail-status").update("[blue]●  Active[/blue]")


# ── main app ──────────────────────────────────────────────────────────────────


class TaskApp(App):
    CSS_PATH = "styling.css"

    BINDINGS = [
        Binding("n", "new_task", "New"),
        Binding("e", "edit_task", "Edit"),
        Binding("d", "delete_task", "Delete"),
        Binding("space", "toggle_complete", "Complete / Undo", show=True),
        Binding("1", "show_active", "Active"),
        Binding("2", "show_complete", "Completed"),
        Binding("q", "quit", "Quit"),
    ]

    current_filter: reactive[str] = reactive("active")

    def __init__(self) -> None:
        super().__init__()
        self.db = TaskDB()
        self.tasks: List[Task] = []

    # ── compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-header"):
            yield Label("◆  TASK BOARD", id="header-title")
            yield Label(datetime.now().strftime("%a, %b %d, %Y"), id="header-date")

        with Horizontal(id="filter-bar"):
            yield Button("● Active", id="btn-active", classes="tab-btn tab-active")
            yield Button("✓ Completed", id="btn-complete", classes="tab-btn")

        with Horizontal(id="main-body"):
            with Container(id="task-list-pane"):
                yield DataTable(id="task-table", cursor_type="row", zebra_stripes=True)
            with Container(id="task-detail-pane"):
                yield TaskDetailPanel(id="task-detail")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.add_columns(" # ", "Name", "P", "Due")
        self._refresh_tasks()

    # ── data helpers ──────────────────────────────────────────────────────────

    def _refresh_tasks(self) -> None:
        self.tasks = (
            self.db.get_all_incomplete_tasks()
            if self.current_filter == "active"
            else self.db.get_all_complete_tasks()
        )

        table = self.query_one("#task-table", DataTable)
        table.clear()

        for task in self.tasks:
            pc = PRIORITY_COLORS.get(task.priority, "white")
            ps = PRIORITY_SHORT.get(task.priority, "?")
            table.add_row(
                str(task.id),
                task.name,
                f"[{pc}]{ps}[/{pc}]",
                _due_markup(task.due_date),
                key=str(task.id),
            )

        if self.tasks:
            table.move_cursor(row=0)
            self._set_detail(self.tasks[0])
        else:
            self._set_detail(None)

    def _set_detail(self, task: Optional[Task]) -> None:
        self.query_one("#task-detail", TaskDetailPanel).update_task(task)

    def _selected_task(self) -> Optional[Task]:
        table = self.query_one("#task-table", DataTable)
        idx = table.cursor_row
        return self.tasks[idx] if 0 <= idx < len(self.tasks) else None

    def _switch_filter(self, f: str) -> None:
        self.current_filter = f
        if f == "active":
            self.query_one("#btn-active").add_class("tab-active")
            self.query_one("#btn-complete").remove_class("tab-active")
        else:
            self.query_one("#btn-complete").add_class("tab-active")
            self.query_one("#btn-active").remove_class("tab-active")
        self._refresh_tasks()

    # ── events ────────────────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self.tasks):
            self._set_detail(self.tasks[idx])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-active":
            self._switch_filter("active")
        elif event.button.id == "btn-complete":
            self._switch_filter("complete")

    # ── actions ───────────────────────────────────────────────────────────────

    def action_new_task(self) -> None:
        def callback(result) -> None:
            if result:
                self.db.add_task(
                    Task(
                        id=None,
                        name=result["name"],
                        description=result["description"],
                        priority=result["priority"],
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        due_date=result["due_date"],
                        is_complete=False,
                        is_hidden=False,
                    )
                )
                self._refresh_tasks()
                self.notify(f'Added "{result["name"]}"', severity="information")

        self.push_screen(AddEditTaskModal(), callback)

    def action_edit_task(self) -> None:
        task = self._selected_task()
        if not task:
            self.notify("No task selected.", severity="warning")
            return

        def callback(result) -> None:
            if result:
                self.db.edit_task(task.id, **result)
                self._refresh_tasks()
                self.notify("Task updated.", severity="information")

        self.push_screen(AddEditTaskModal(task=task), callback)

    def action_delete_task(self) -> None:
        task = self._selected_task()
        if not task:
            self.notify("No task selected.", severity="warning")
            return

        def callback(confirmed: bool) -> None:
            if confirmed:
                self.db.remove_task(task.id)
                self._refresh_tasks()
                self.notify(f'Removed "{task.name}"', severity="warning")

        self.push_screen(ConfirmModal(f'Remove  "{task.name}" ?'), callback)

    def action_toggle_complete(self) -> None:
        task = self._selected_task()
        if not task:
            self.notify("No task selected.", severity="warning")
            return
        new_val = not task.is_complete
        self.db.edit_task(task.id, is_complete=int(new_val))
        label = "Completed" if new_val else "Reopened"
        self.notify(f'{label}  "{task.name}"', severity="information")
        self._refresh_tasks()

    def action_show_active(self) -> None:
        self._switch_filter("active")

    def action_show_complete(self) -> None:
        self._switch_filter("complete")


if __name__ == "__main__":
    TaskApp().run()
