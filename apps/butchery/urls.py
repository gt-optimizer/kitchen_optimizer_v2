from django.urls import path
from . import views

app_name = "butchery"

urlpatterns = [
    # Gabarits
    path("templates/",                          views.template_list,   name="template_list"),
    path("templates/add/",                      views.template_add,    name="template_add"),
    path("templates/<int:pk>/",                 views.template_detail, name="template_detail"),
    path("templates/<int:pk>/edit/",            views.template_edit,   name="template_edit"),
    path("templates/<int:pk>/lines/add/",       views.template_line_add,  name="template_line_add"),
    path("templates/<int:pk>/lines/<int:line_pk>/edit/",
         views.template_line_edit, name="template_line_edit"),
    path("templates/<int:pk>/lines/<int:line_pk>/delete/",
         views.template_line_delete, name="template_line_delete"),

    # Sessions
    path("sessions/",                           views.session_list,    name="session_list"),
    path("sessions/add/",                       views.session_add,     name="session_add"),
    path("sessions/<int:pk>/",                  views.session_detail,  name="session_detail"),
    path("sessions/<int:pk>/edit/",             views.session_edit,    name="session_edit"),
    path("sessions/<int:pk>/close/",            views.session_close,   name="session_close"),
    path("sessions/<int:pk>/validate/",         views.session_validate, name="session_validate"),

    # Lignes de session (saisie progressive)
    path("sessions/<int:pk>/lines/add/",        views.session_line_add,    name="session_line_add"),
    path("sessions/<int:pk>/lines/<int:line_pk>/edit/",
         views.session_line_edit,   name="session_line_edit"),
    path("sessions/<int:pk>/lines/<int:line_pk>/delete/",
         views.session_line_delete, name="session_line_delete"),
    path("sessions/<int:pk>/lines/<int:line_pk>/confirm/",
         views.session_line_confirm, name="session_line_confirm"),

    # Historique rendements
    path("yields/",                             views.yield_list,      name="yield_list"),
    path("yields/<int:pk>/",                    views.yield_detail,    name="yield_detail"),
]