from django.urls import path

from scheduling.ui import views

urlpatterns = [
    # Calendar (Month View)
    path("", views.month_view, name="calendar"),

    # Assignments
    path("assign/<int:assignment_id>/confirm/", views.confirm_assignment, name="confirm_assignment"),
    path("assign/<int:assignment_id>/swap/", views.swap_assignment, name="swap_assignment"),
    path("assign/add/<int:service_id>/", views.assignment_add, name="assignment_add"),
    path("generate/", views.generate_schedule_view, name="generate_schedule_view"),

    # Ranking
    path("ranking/candidates/", views.ranking_candidates_view, name="ranking_candidates"),

    # Services
    path("services/new/", views.service_create, name="service_create"),
    path("services/<int:service_id>/edit/", views.service_edit, name="service_edit"),
    path("services/<int:service_id>/delete/", views.service_delete, name="service_delete"),

    # Members
    path("members/", views.members_list, name="members_list"),
    path("members/<int:member_id>/edit/", views.member_edit, name="member_edit"),
]
