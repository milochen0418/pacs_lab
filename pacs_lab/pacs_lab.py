import reflex as rx

from pacs_lab.pages.detail import detail_page
from pacs_lab.pages.home import home_page
from pacs_lab.pages.wizard import wizard_page
from pacs_lab.states.lab_state import LabState

app = rx.App(
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
)
app.add_page(home_page, route="/", title="PACS Lab", on_load=LabState.load_home)
app.add_page(wizard_page, route="/new", title="New practice PACS · PACS Lab", on_load=[LabState.load_home, LabState.load_wizard])
app.add_page(detail_page, route="/pacs/[pacs_id]", title="PACS · PACS Lab", on_load=LabState.load_detail)
