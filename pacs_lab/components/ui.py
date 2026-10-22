"""Pieces shared by the pages: the frame, badges, the image picker, a job's progress."""

import reflex as rx

from pacs_lab.states.lab_state import LabState, LibRow, LineRow, PatientRow, StarterRow, StepRow

S = LabState
BTN = "inline-flex items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap px-3 py-1.5 disabled:opacity-50"
PRIMARY = f"{BTN} text-white bg-blue-600 hover:bg-blue-700"
SECONDARY = f"{BTN} text-gray-700 bg-white border border-gray-300 hover:bg-gray-50"
CARD = "bg-white rounded-xl border border-gray-200 shadow-sm"


def layout(*content: rx.Component) -> rx.Component:
    return rx.el.div(
        rx.el.header(
            rx.el.div(
                rx.el.a(
                    rx.icon("server-cog", size=24, class_name="text-blue-600"),
                    rx.el.span(S.t["app_title"], class_name="text-lg font-bold text-gray-900"),
                    href="/",
                    class_name="flex items-center gap-2",
                ),
                rx.el.button(
                    rx.icon("languages", size=16),
                    S.t["lang_other"],
                    on_click=S.toggle_lang,
                    class_name=SECONDARY,
                ),
                class_name="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between",
            ),
            class_name="bg-white border-b border-gray-200",
        ),
        rx.el.main(
            rx.cond(
                S.docker_error_text != "",
                rx.el.div(
                    rx.icon("triangle-alert", size=18, class_name="shrink-0 mt-0.5"),
                    rx.el.p(S.docker_error_text),
                    class_name="flex gap-2 p-4 mb-6 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm",
                ),
            ),
            *content,
            class_name="max-w-5xl mx-auto px-4 sm:px-6 py-6",
        ),
        delete_dialog(),
        class_name="min-h-screen bg-gray-50 font-['Inter'] text-gray-900",
    )


def status_pill(status) -> rx.Component:
    return rx.match(
        status,
        ("running", _pill(S.t["status_running"], "bg-green-500", "text-green-700 bg-green-50")),
        ("exited", _pill(S.t["status_exited"], "bg-gray-400", "text-gray-600 bg-gray-100")),
        ("restarting", _pill(S.t["status_restarting"], "bg-amber-500", "text-amber-700 bg-amber-50")),
        ("created", _pill(S.t["status_created"], "bg-gray-400", "text-gray-600 bg-gray-100")),
        _pill(status, "bg-red-500", "text-red-700 bg-red-50"),
    )


def _pill(text, dot: str, colors: str) -> rx.Component:
    return rx.el.span(
        rx.el.span(class_name=f"h-2 w-2 rounded-full {dot}"),
        text,
        class_name=f"inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold {colors}",
    )


def kind_badge(kind) -> rx.Component:
    return rx.el.span(
        S.t["kind_" + kind],
        class_name="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 text-xs font-semibold",
    )


def delete_dialog() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title(S.t["delete_title"]),
            rx.alert_dialog.description(
                rx.el.p(rx.el.strong(S.delete_label), class_name="mb-2"),
                rx.el.p(S.t["delete_body"]),
                class_name="text-gray-600 text-sm",
            ),
            rx.el.div(
                rx.alert_dialog.cancel(rx.el.button(S.t["btn_cancel"], on_click=S.cancel_delete, class_name=SECONDARY)),
                rx.alert_dialog.action(
                    rx.el.button(
                        S.t["btn_delete"], on_click=S.confirm_delete,
                        class_name=f"{BTN} text-white bg-red-600 hover:bg-red-700",
                    )
                ),
                class_name="flex justify-end gap-3 mt-4",
            ),
        ),
        open=S.delete_name != "",
    )


# -- choosing images ---------------------------------------------------------------------------

def _check(checked, on_change) -> rx.Component:
    return rx.el.input(type="checkbox", checked=checked, on_change=on_change, class_name="h-4 w-4 accent-blue-600 shrink-0")


def _starter_row(row: StarterRow) -> rx.Component:
    return rx.el.label(
        _check(S.pick_starter.contains(row.key), lambda _v: S.toggle_starter(row.key)),
        rx.el.div(
            rx.el.p(S.t["starter_" + row.key], class_name="text-sm font-medium text-gray-900"),
            rx.el.p(row.detail, class_name="text-xs text-gray-500"),
            class_name="flex-1 min-w-0",
        ),
        rx.el.span(row.mb, class_name="text-xs text-gray-500 whitespace-nowrap"),
        class_name="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 cursor-pointer",
    )


def _library_row(row: LibRow) -> rx.Component:
    return rx.el.label(
        _check(S.pick_library.contains(row.uid), lambda _v: S.toggle_library(row.uid)),
        rx.el.span(row.modality, class_name="px-2 py-0.5 rounded-md bg-gray-100 text-gray-700 text-xs font-semibold w-14 text-center shrink-0"),
        rx.el.div(
            rx.el.p(row.description, class_name="text-sm text-gray-900 truncate"),
            rx.el.p(row.detail, class_name="text-xs text-gray-500"),
            class_name="flex-1 min-w-0",
        ),
        rx.el.span(row.mb, class_name="text-xs text-gray-500 whitespace-nowrap"),
        class_name="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 cursor-pointer",
    )


def data_picker() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.h3(S.t["data_starter"], class_name="font-semibold text-gray-900"),
            rx.el.p(S.t["data_starter_desc"], class_name="text-sm text-gray-500 mt-0.5"),
            class_name="px-4 pt-4 pb-2",
        ),
        rx.el.div(rx.foreach(S.starter_rows, _starter_row), class_name="divide-y divide-gray-100"),
        rx.el.div(
            rx.el.h3(S.t["data_library"], class_name="font-semibold text-gray-900"),
            rx.el.p(S.t["data_library_desc"], class_name="text-sm text-gray-500 mt-0.5"),
            class_name="px-4 pt-5 pb-2 border-t border-gray-100",
        ),
        rx.match(
            S.library_state,
            ("none", rx.el.p(S.t["data_library_none"], class_name="px-4 pb-4 text-sm text-gray-500")),
            ("off", rx.el.p(S.t["data_library_off"], class_name="px-4 pb-4 text-sm text-gray-500")),
            rx.el.div(rx.foreach(S.library_view, _library_row), class_name="divide-y divide-gray-100 max-h-72 overflow-y-auto"),
        ),
        rx.el.label(
            _check(S.relabel, lambda _v: S.toggle_relabel()),
            rx.el.div(
                rx.el.p(S.t["relabel"], class_name="text-sm font-medium text-gray-900"),
                rx.el.p(S.t["relabel_hint"], class_name="text-xs text-gray-500 mt-0.5"),
            ),
            class_name="flex items-start gap-3 m-4 p-3 rounded-lg bg-blue-50/60 border border-blue-100 cursor-pointer",
        ),
        rx.el.p(S.summary_data, class_name="px-4 pb-4 text-sm font-medium text-gray-700"),
        class_name=CARD,
    )


# -- a job's progress ----------------------------------------------------------------------------

def _step_row(row: StepRow) -> rx.Component:
    icon = rx.match(
        row.state,
        ("done", rx.icon("circle-check", size=18, class_name="text-green-600")),
        ("running", rx.icon("loader-circle", size=18, class_name="text-blue-600 animate-spin")),
        ("failed", rx.icon("circle-x", size=18, class_name="text-red-600")),
        ("skipped", rx.icon("circle-minus", size=18, class_name="text-gray-300")),
        rx.icon("circle", size=18, class_name="text-gray-300"),
    )
    return rx.el.li(
        icon,
        rx.el.span(
            row.label,
            class_name=rx.cond(row.state == "waiting", "text-sm text-gray-400", "text-sm text-gray-800"),
        ),
        rx.el.span(row.detail, class_name="ml-auto text-xs font-mono text-gray-500"),
        class_name="flex items-center gap-3 py-1.5",
    )


def line(row: LineRow) -> rx.Component:
    return rx.el.li(
        rx.match(
            row.state,
            ("ok", rx.icon("circle-check", size=16, class_name="text-green-600 shrink-0 mt-0.5")),
            ("fail", rx.icon("circle-x", size=16, class_name="text-red-600 shrink-0 mt-0.5")),
            rx.icon("info", size=16, class_name="text-blue-600 shrink-0 mt-0.5"),
        ),
        rx.el.span(row.text),
        class_name="flex gap-2 text-sm text-gray-700",
    )


def _patient_row(row: PatientRow) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            rx.el.button(
                rx.el.span(row.id, class_name="font-mono font-semibold"),
                rx.icon("copy", size=13, class_name="text-gray-400"),
                on_click=S.copy(row.id),
                class_name="inline-flex items-center gap-1.5 hover:text-blue-700",
            ),
            class_name="px-3 py-1.5",
        ),
        rx.el.td(row.name, class_name="px-3 py-1.5"),
        rx.el.td(row.studies, class_name="px-3 py-1.5 text-gray-500"),
        class_name="text-sm",
    )


def job_progress() -> rx.Component:
    return rx.el.div(
        rx.el.ul(rx.foreach(S.job_steps, _step_row), class_name="px-4 py-3"),
        rx.cond(
            S.job_error != "",
            rx.el.div(
                rx.el.p(S.t["failed_title"], class_name="font-semibold"),
                rx.el.p(S.job_error, class_name="mt-1 whitespace-pre-wrap break-words"),
                class_name="mx-4 mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-800",
            ),
        ),
        rx.cond(
            S.job_checks.length() > 0,
            rx.el.ul(rx.foreach(S.job_checks, line), class_name="mx-4 mb-4 flex flex-col gap-1.5"),
        ),
        rx.cond(
            S.job_patients.length() > 0,
            rx.el.div(
                rx.el.p(S.t["patients_title"], class_name="text-sm font-semibold text-gray-700 mb-1"),
                rx.el.table(rx.el.tbody(rx.foreach(S.job_patients, _patient_row)), class_name="min-w-full"),
                class_name="mx-4 mb-4",
            ),
        ),
        class_name=CARD,
    )
