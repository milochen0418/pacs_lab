"""One practice PACS: what to type into DICOM Data Explorer, what it holds, its web page and log."""

import reflex as rx

from pacs_lab.components.ui import BTN, CARD, PRIMARY, SECONDARY, S, data_picker, job_progress, kind_badge, layout, status_pill
from pacs_lab.states.lab_state import CardRow, FieldRow, StudyRow


def _field(f: FieldRow) -> rx.Component:
    shown = ~f.secret | S.revealed.contains(f.key)
    return rx.el.div(
        rx.el.div(f.label, class_name="font-mono text-xs font-semibold text-gray-600 sm:w-56 shrink-0"),
        rx.el.div(
            rx.el.code(rx.cond(shown, f.value, "••••••••••"), class_name="font-mono text-sm text-gray-900 break-all"),
            rx.cond(
                f.secret,
                rx.el.button(rx.icon("eye", size=14), on_click=S.reveal(f.key), title=S.t["show"], class_name="text-gray-400 hover:text-gray-700"),
            ),
            rx.el.button(
                rx.icon("copy", size=14), on_click=S.copy(f.value), title=S.t["copy"],
                class_name="text-gray-400 hover:text-blue-700",
            ),
            class_name="flex items-center gap-2 flex-1 min-w-0",
        ),
        rx.el.p(f.hint, class_name="text-xs text-gray-500 sm:w-64"),
        class_name="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 py-2.5 border-b border-gray-100 last:border-b-0",
    )


def _card(c: CardRow) -> rx.Component:
    return rx.el.div(
        rx.el.h3(c.title, class_name="font-semibold text-gray-900 mb-1"),
        rx.foreach(c.fields, _field),
        class_name=f"{CARD} p-4",
    )


def _study(row: StudyRow) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            rx.el.button(
                rx.el.span(row.patient_id, class_name="font-mono font-semibold"),
                rx.icon("copy", size=13, class_name="text-gray-400"),
                on_click=S.copy(row.patient_id),
                class_name="inline-flex items-center gap-1.5 hover:text-blue-700",
            ),
            class_name="px-3 py-2",
        ),
        rx.el.td(row.patient_name, class_name="px-3 py-2"),
        rx.el.td(row.date, class_name="px-3 py-2 whitespace-nowrap"),
        rx.el.td(row.description, class_name="px-3 py-2 text-gray-600"),
        rx.el.td(row.modalities, class_name="px-3 py-2"),
        rx.el.td(row.images, class_name="px-3 py-2 text-right"),
        class_name="text-sm border-t border-gray-100",
    )


def _contents() -> rx.Component:
    head = rx.el.tr(
        *[rx.el.th(S.t[k], class_name="px-3 py-2 text-left text-xs font-semibold text-gray-500") for k in
          ("col_id", "col_patient", "col_date", "col_desc", "col_mod", "col_images")],
    )
    return rx.match(
        S.studies_state,
        ("loading", rx.el.p(S.t["loading"], class_name="text-sm text-gray-500 p-4")),
        ("off", rx.el.p(S.t["contents_off"], class_name="text-sm text-gray-500 p-4")),
        rx.cond(
            S.studies.length() > 0,
            rx.el.div(
                rx.el.table(rx.el.thead(head), rx.el.tbody(rx.foreach(S.studies, _study)), class_name="min-w-full"),
                class_name="overflow-x-auto",
            ),
            rx.el.p(S.t["contents_empty"], class_name="text-sm text-gray-500 p-4"),
        ),
    )


def _add_dialog() -> rx.Component:
    working = S.job_running | S.job_done_ok | S.job_failed
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(S.t["add_data_title"]),
            rx.el.div(rx.cond(working, job_progress(), data_picker()), class_name="mt-3 max-h-[70vh] overflow-y-auto"),
            rx.el.div(
                rx.dialog.close(rx.el.button(rx.cond(working, "OK", S.t["btn_cancel"]), disabled=S.job_running, class_name=SECONDARY)),
                rx.cond(
                    ~working,
                    rx.el.button(
                        rx.icon("upload", size=15), S.t["add_data"], on_click=S.add_data,
                        disabled=S.picked_series == 0, class_name=f"{PRIMARY} px-4 py-2",
                    ),
                ),
                class_name="flex justify-end gap-3 mt-4",
            ),
            class_name="max-w-2xl",
        ),
        open=S.add_open,
        on_open_change=S.set_add_open,
    )


def detail_page() -> rx.Component:
    d = S.d
    busy = S.busy == d.name
    return layout(
        rx.el.a(rx.icon("arrow-left", size=15), S.t["back_home"], href="/", class_name="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900 mb-3"),
        rx.el.div(
            rx.el.div(
                rx.el.h1(d.label, class_name="text-2xl font-bold text-gray-900"),
                kind_badge(d.kind),
                status_pill(d.status),
                class_name="flex flex-wrap items-center gap-2",
            ),
            rx.el.div(
                rx.cond(
                    d.status == "running",
                    rx.el.button(rx.icon("square", size=14), S.t["btn_stop"], on_click=S.power(d.name, False), disabled=busy, class_name=SECONDARY),
                    rx.el.button(rx.icon("play", size=14), S.t["btn_start"], on_click=S.power(d.name, True), disabled=busy, class_name=SECONDARY),
                ),
                rx.el.button(
                    rx.icon("trash-2", size=15), on_click=S.ask_delete(d.name, d.label), disabled=busy, title=S.t["btn_delete"],
                    class_name=f"{BTN} text-gray-500 border border-gray-300 hover:text-red-600 hover:bg-red-50",
                ),
                class_name="flex items-center gap-2",
            ),
            class_name="flex flex-wrap items-center justify-between gap-3",
        ),
        rx.el.p(
            f"{d.name} · AE {d.aet} · DICOM 127.0.0.1:{d.dicom_port}",
            rx.cond(d.http_port > 0, f" · web localhost:{d.http_port}", ""),
            class_name="text-xs font-mono text-gray-500 mt-1 mb-4",
        ),
        rx.el.div(
            rx.el.span(S.t["place_now"], class_name="font-semibold"),
            rx.el.span(rx.cond(d.explorer_at == "appstore", S.t["place_appstore"], S.t["place_mac"])),
            rx.el.button(
                rx.icon("arrow-left-right", size=14),
                rx.cond(d.explorer_at == "appstore", S.t["switch_to_mac"], S.t["switch_to_appstore"]),
                on_click=S.switch_place(rx.cond(d.explorer_at == "appstore", "mac", "appstore")),
                disabled=busy,
                title=S.t["switch_note"],
                class_name=f"{SECONDARY} ml-auto",
            ),
            class_name="flex flex-wrap items-center gap-2 p-3 mb-6 rounded-lg bg-white border border-gray-200 text-sm text-gray-700",
        ),
        rx.el.h2(S.t["settings_title"], class_name="text-lg font-bold text-gray-900"),
        rx.el.p(S.t["settings_intro"], class_name="text-sm text-gray-600 mt-1 mb-3"),
        rx.el.div(rx.foreach(S.cards, _card), class_name="flex flex-col gap-4 mb-8"),
        rx.el.div(
            rx.el.h2(S.t["try_title"], class_name="text-lg font-bold text-gray-900"),
            rx.el.button(
                rx.icon("upload", size=15), S.t["add_data"], on_click=S.set_add_open(True),
                disabled=d.status != "running", class_name=SECONDARY,
            ),
            class_name="flex flex-wrap items-center justify-between gap-2",
        ),
        rx.el.p(S.t["try_body"], class_name="text-sm text-gray-600 mt-1 mb-2"),
        rx.el.div(
            rx.el.p(S.t["contents_title"], class_name="px-3 pt-3 text-xs font-semibold text-gray-500"),
            _contents(),
            class_name=f"{CARD} mb-8",
        ),
        rx.el.h2(S.t["web_title"], class_name="text-lg font-bold text-gray-900 mb-2"),
        rx.cond(
            d.http_port > 0,
            rx.el.div(
                rx.el.p(S.t["web_body"], class_name="text-sm text-gray-600 flex-1"),
                rx.el.a(rx.icon("external-link", size=15), S.t["btn_web"], href=d.web_page, target="_blank", class_name=f"{PRIMARY} px-4 py-2"),
                class_name=f"{CARD} p-4 mb-8 flex flex-wrap items-center gap-3",
            ),
            rx.el.p(S.t["mini_no_web"], class_name=f"{CARD} p-4 mb-8 text-sm text-gray-600"),
        ),
        rx.el.h2(S.t["logs_title"], class_name="text-lg font-bold text-gray-900 mb-2"),
        rx.el.div(
            rx.el.button(rx.icon("scroll-text", size=15), S.t["logs_show"], on_click=S.show_logs, class_name=SECONDARY),
            rx.cond(
                S.logs != "",
                rx.el.pre(S.logs, class_name="mt-3 p-3 rounded-lg bg-gray-900 text-gray-100 text-xs overflow-x-auto max-h-96 overflow-y-auto"),
            ),
            class_name="mb-8",
        ),
        _add_dialog(),
    )
