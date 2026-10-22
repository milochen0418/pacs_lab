"""The list of practice PACS."""

import reflex as rx

from pacs_lab.components.ui import BTN, CARD, PRIMARY, SECONDARY, S, kind_badge, layout, status_pill
from pacs_lab.states.lab_state import PacsRow


def _pacs_card(p: PacsRow) -> rx.Component:
    busy = S.busy == p.name
    return rx.el.div(
        rx.el.div(
            rx.icon("server", size=22, class_name="text-gray-400 shrink-0"),
            rx.el.div(
                rx.el.div(
                    rx.el.a(p.label, href=f"/pacs/{p.name}", class_name="font-semibold text-gray-900 hover:text-blue-700"),
                    kind_badge(p.kind),
                    status_pill(p.status),
                    class_name="flex flex-wrap items-center gap-2",
                ),
                rx.el.p(
                    f"AE {p.aet} · DICOM 127.0.0.1:{p.dicom_port}",
                    rx.cond(p.http_port > 0, f" · web localhost:{p.http_port}", ""),
                    class_name="text-xs font-mono text-gray-500 mt-1",
                ),
                class_name="flex-1 min-w-0",
            ),
            class_name="flex items-start gap-3",
        ),
        rx.el.div(
            rx.el.a(rx.icon("list-checks", size=15), S.t["btn_settings"], href=f"/pacs/{p.name}", class_name=PRIMARY),
            rx.cond(
                (p.web_page != "") & (p.status == "running"),
                rx.el.a(rx.icon("external-link", size=15), S.t["btn_web"], href=p.web_page, target="_blank", class_name=SECONDARY),
            ),
            rx.cond(
                p.status == "running",
                rx.el.button(rx.icon("square", size=14), S.t["btn_stop"], on_click=S.power(p.name, False), disabled=busy, class_name=SECONDARY),
                rx.el.button(rx.icon("play", size=14), S.t["btn_start"], on_click=S.power(p.name, True), disabled=busy, class_name=SECONDARY),
            ),
            rx.el.button(
                rx.icon("trash-2", size=15),
                on_click=S.ask_delete(p.name, p.label),
                disabled=busy,
                title=S.t["btn_delete"],
                class_name=f"{BTN} text-gray-500 border border-gray-300 hover:text-red-600 hover:bg-red-50",
            ),
            class_name="flex flex-wrap items-center gap-2 mt-3 pl-9",
        ),
        class_name=f"{CARD} p-4",
    )


def home_page() -> rx.Component:
    return layout(
        rx.el.p(S.t["app_tagline"], class_name="text-gray-600 mb-4"),
        rx.el.details(
            rx.el.summary(S.t["what_title"], class_name="cursor-pointer font-semibold text-gray-900"),
            rx.el.p(S.t["what_body"], class_name="text-sm text-gray-700 mt-2 leading-relaxed"),
            class_name=f"{CARD} p-4 mb-6",
            open=True,
        ),
        rx.el.div(
            rx.el.h1(S.t["my_pacs"], class_name="text-xl font-bold text-gray-900"),
            rx.el.div(
                rx.el.button(rx.icon("refresh-cw", size=15), S.t["refresh"], on_click=S.load_home, class_name=SECONDARY),
                rx.el.a(rx.icon("plus", size=16), S.t["new_pacs"], href="/new", class_name=f"{PRIMARY} px-4 py-2"),
                class_name="flex items-center gap-2",
            ),
            class_name="flex flex-wrap items-center justify-between gap-3 mb-2",
        ),
        rx.cond(S.where_text != "", rx.el.p(S.where_text, class_name="text-sm text-gray-500 mb-4")),
        rx.cond(
            S.pacs.length() > 0,
            rx.el.div(rx.foreach(S.pacs, _pacs_card), class_name="flex flex-col gap-3"),
            rx.el.div(
                rx.icon("server", size=36, class_name="text-gray-300 mb-3"),
                rx.el.h3(S.t["empty_title"], class_name="text-lg font-medium text-gray-900"),
                rx.el.p(S.t["empty_body"], class_name="text-gray-500 mt-1 max-w-lg text-center"),
                class_name="flex flex-col items-center justify-center py-14 bg-white rounded-xl border border-dashed border-gray-300",
            ),
        ),
    )
