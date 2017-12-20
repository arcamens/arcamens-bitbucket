from django.views.generic.base import RedirectView
from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^index/$', views.Index.as_view(), name='index'),
    url(r'^switch-organization/(?P<organization_id>.+)/', views.SwitchOrganization.as_view(), name='switch-organization'),
    url(r'^update-user-information/', views.UpdateUserInformation.as_view(), name='update-user-information'),
    url(r'^create-organization/(?P<user_id>.+)/', views.CreateOrganization.as_view(), name='create-organization'),
    url(r'^update-organization/(?P<organization_id>.+)/', views.UpdateOrganization.as_view(), name='update-organization'),
    url(r'^delete-organization/(?P<organization_id>.+)/', views.DeleteOrganization.as_view(), name='delete-organization'),
    url(r'^list-users/(?P<organization_id>.+)', views.ListUsers.as_view(), name='list-users'),
    url(r'^list-user-tags/(?P<user_id>.+)', views.ListUserTags.as_view(), name='list-user-tags'),
    url(r'^list-events/', views.ListEvents.as_view(), name='list-events'),
    url(r'^list-tags/', views.ListTags.as_view(), name='list-tags'),
    url(r'^bind-tag/(?P<user_id>.+)/', views.BindTag.as_view(), name='bind-tag'),
    url(r'^unbind-user-tag/(?P<tag_id>.+)/(?P<user_id>.+)/', views.UnbindUserTag.as_view(), name='unbind-user-tag'),
    url(r'^create-tag/', views.CreateTag.as_view(), name='create-tag'),

]














