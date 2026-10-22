"""New practice PACS: kind → images → name and place → start."""

import reflex as rx

from pacs_lab.components.ui import CARD, PRIMARY, SECONDARY, S, data_picker, job_progress, layout
from pacs_lab.states.lab_state import KindRow


def _stepper() -> rx.Component:
    def dot(n: int, key: str) -> rx.Component:
        active = S.wiz_step == n
        done = S.wiz_step > n
        return rx.el.button(
            rx.el.span(
                rx.cond(done, rx.icon("check", size=14), str(n)),
                class_name=rx.cond(
                    active | done,
                    "h-7 w-7 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold",
                    "h-7 w-7 rounded-full bg-gray-200 text-gray-600 flex items-center justify-center text-sm font-semibold",
                ),
            ),
            rx.el.span(S.t[key], class_name=rx.cond(active, "text-sm font-semibold text-gray-900", "text-sm text-gray-500")),
            on_click=S.wiz_go(n),
            class_name="flex items-center gap-2",
        )

    bar = rx.el.span(class_name="h-px w-6 sm:w-10 bg-gray-300")
    return rx.el.div(
        dot(1, "wiz_step_kind"), bar, dot(2, "wiz_step_data"), bar, dot(3, "wiz_step_place"), bar, dot(4, "wiz_step_run"),
        class_name="flex flex-wrap items-center gap-2 mb-6",
    )


def _feature(ok, label: str) -> rx.Component:
    return rx.el.span(
        rx.cond(ok, rx.icon("check", size=13, class_name="text-green-600"), rx.icon("x", size=13, class_name="text-gray-400")),
        label,
        class_name=rx.cond(ok, "inline-flex items-center gap-1 text-xs text-gray-700", "inline-flex items-center gap-1 text-xs text-gray-400"),
    )


def _kind_card(k: KindRow) -> rx.Component:
    chosen = S.wiz_kind == k.id
    return rx.el.button(
        rx.el.div(
            rx.cond(chosen, rx.icon("circle-dot", size=18, class_name="text-blue-600"), rx.icon("circle", size=18, class_name="text-gray-300")),
            rx.el.span(S.t["kind_" + k.id], class_name="font-semibold text-gray-900"),
            class_name="flex items-center gap-2",
        ),
        rx.el.p(S.t[f"kind_{k.id}_desc"], class_name="text-sm text-gray-600 mt-2 text-left"),
        rx.el.div(
            _feature(k.dicomweb, "DICOMweb"), _feature(k.can_get, "C-GET"), _feature(True, "C-MOVE"), _feature(k.web, "Web"),
            rx.el.span(k.memory, class_name="text-xs text-gray-400 ml-auto"),
            class_name="flex flex-wrap items-center gap-3 mt-3",
        ),
        on_click=S.choose_kind(k.id),
        class_name=rx.cond(
            chosen,
            "w-full p-4 rounded-xl border-2 border-blue-600 bg-blue-50/40 text-left",
            "w-full p-4 rounded-xl border-2 border-gray-200 bg-white hover:border-gray-300 text-left",
        ),
    )


def _place(value: str, key: str) -> rx.Component:
    chosen = S.wiz_place == value
    return rx.el.button(
        rx.cond(chosen, rx.icon("circle-dot", size=18, class_name="text-blue-600"), rx.icon("circle", size=18, class_name="text-gray-300")),
        rx.el.span(S.t[key], class_name="text-sm text-gray-900"),
        rx.cond(
            S.explorer_where == value,
            rx.el.span(S.t["detected"], class_name="px-1.5 py-0.5 rounded bg-green-50 text-green-700 text-xs font-semibold"),
        ),
        on_click=S.set_place(value),
        class_name="flex items-center gap-2 w-full px-3 py-2.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50",
    )


def _step_place() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.label(S.t["wiz_name"], class_name="block text-sm font-semibold text-gray-700 mb-1"),
            rx.el.input(
                value=S.wiz_label,
                on_change=S.set_label,
                placeholder=S.default_label,
                class_name="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none",
            ),
            class_name=f"{CARD} p-4",
        ),
        rx.el.div(
            rx.el.h3(S.t["place_title"], class_name="font-semibold text-gray-900"),
            rx.el.p(S.t["place_hint"], class_name="text-sm text-gray-500 mt-0.5 mb-3"),
            rx.el.div(_place("appstore", "place_appstore"), _place("mac", "place_mac"), class_name="flex flex-col gap-2"),
            class_name=f"{CARD} p-4",
        ),
        rx.el.div(
            rx.el.p(S.t["summary_title"], class_name="font-semibold text-gray-900"),
            rx.el.ul(
                rx.el.li(S.t["kind_" + S.wiz_kind]),
                rx.el.li(rx.cond(S.wiz_label != "", S.wiz_label, S.default_label)),
                rx.el.li(S.summary_data),
                class_name="list-disc pl-5 text-sm text-gray-700 mt-1",
            ),
            class_name="p-4 rounded-xl bg-blue-50/60 border border-blue-100",
        ),
        class_name="flex flex-col gap-4",
    )


def _done() -> rx.Component:
    return rx.cond(
        S.job_done_ok,
        rx.el.div(
            rx.el.div(
                rx.icon("party-popper", size=22, class_name="text-green-600"),
                rx.el.div(
                    rx.el.p(S.t["done_title"], class_name="font-semibold text-gray-900"),
                    rx.el.p(S.t["done_body"], class_name="text-sm text-gray-600"),
                ),
                class_name="flex items-center gap-3",
            ),
            rx.el.div(
                rx.el.a(rx.icon("list-checks", size=16), S.t["go_settings"], href=f"/pacs/{S.job_pacs}", class_name=f"{PRIMARY} px-4 py-2"),
                rx.el.button(S.t["wiz_again"], on_click=S.load_wizard, class_name=SECONDARY),
                class_name="flex gap-2",
            ),
            class_name="flex flex-wrap items-center justify-between gap-3 p-4 mb-4 rounded-xl bg-green-50 border border-green-200",
        ),
        rx.cond(
            S.job_failed & (S.job_pacs != ""),
            rx.el.div(rx.el.a(S.t["go_settings"], href=f"/pacs/{S.job_pacs}", class_name=SECONDARY), class_name="mb-4"),
        ),
    )


def wizard_page() -> rx.Component:
    step = S.wiz_step
    return layout(
        rx.el.h1(S.t["new_pacs"], class_name="text-xl font-bold text-gray-900 mb-4"),
        _stepper(),
        rx.match(
            step,
            (1, rx.el.div(rx.foreach(S.kinds, _kind_card), class_name="grid gap-3")),
            (2, data_picker()),
            (3, _step_place()),
            rx.el.div(_done(), job_progress()),
        ),
        rx.cond(
            step < 4,
            rx.el.div(
                rx.cond(step > 1, rx.el.button(S.t["wiz_back"], on_click=S.wiz_go(step - 1), class_name=SECONDARY), rx.el.span()),
                rx.cond(
                    step < 3,
                    rx.el.button(S.t["wiz_next"], rx.icon("arrow-right", size=16), on_click=S.wiz_go(step + 1), class_name=f"{PRIMARY} px-4 py-2"),
                    rx.el.button(rx.icon("rocket", size=16), S.t["wiz_start"], on_click=S.create, class_name=f"{PRIMARY} px-5 py-2"),
                ),
                class_name="flex items-center justify-between mt-6",
            ),
        ),
    )
