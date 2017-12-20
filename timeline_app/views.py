from core_app.views import AuthenticatedView, GuardianView
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.generic import View
from timeline_app import models
from timeline_app import forms
from django.db.models import Q
from core_app import ws
import core_app.models
import timeline_app.models
import post_app.models

# Create your views here.

class Timeline(GuardianView):
    """
    """

    def get(self, request, timeline_id):
        timeline = models.Timeline.objects.get(id=timeline_id)
        return render(request, 'timeline_app/timeline.html', 
        {'timeline':timeline})

class ListPosts(GuardianView):
    """
    """

    def get(self, request, timeline_id):
        timeline  = models.Timeline.objects.get(id=timeline_id)
        user      = timeline_app.models.User.objects.get(id=self.user_id)
        filter, _ = post_app.models.PostFilter.objects.get_or_create(
        user=user, timeline=timeline)

        posts = timeline.posts.filter((Q(label__icontains=filter.pattern) | \
        Q(description__icontains=filter.pattern)) & Q(done=filter.done) if filter.status else Q(ancestor=timeline))

        # posts    = timeline.posts.all().order_by('-created')
        return render(request, 'timeline_app/list-posts.html', 
        {'timeline':timeline, 'posts':posts, 'filter': filter})

class ListAllPosts(GuardianView):
    """
    """

    def get(self, request, user_id):
        user = core_app.models.User.objects.get(id=self.user_id)

        filter, _ = post_app.models.GlobalPostFilter.objects.get_or_create(
        user=user, organization=user.default)

        timelines = user.timelines.filter(organization=user.default)
        posts     = post_app.models.Post.objects.filter(ancestor__in = timelines)

        posts     = posts.filter((Q(label__icontains=filter.pattern) | \
        Q(description__icontains=filter.pattern)) & Q(done=filter.done)) if filter.status else posts

        posts    = posts.order_by('-created')

        # Missing filters.
        total = post_app.models.Post.objects.filter(
        ancestor__in = user.timelines.all())

        return render(request, 'timeline_app/list-all-posts.html', 
        {'user':user, 'posts':posts, 'total': total, 'filter': filter})

class CreateTimeline(GuardianView):
    """
    """

    def get(self, request, organization_id):
        form = forms.TimelineForm()
        return render(request, 'timeline_app/create-timeline.html', 
        {'form':form, 'user_id': self.user_id, 'organization_id':organization_id})

    def post(self, request, organization_id):
        form = forms.TimelineForm(request.POST)

        if not form.is_valid():
            return render(request, 'timeline_app/create-timeline.html',
                        {'form': form, 'user_id':self.user_id, 
                                'organization_id': organization_id}, status=400)

        organization = timeline_app.models.Organization.objects.get(id=organization_id)
        user         = timeline_app.models.User.objects.get(id=self.user_id)
        record       = form.save(commit=False)
        record.owner = user
        record.organization  = organization
        form.save()
        record.users.add(user)
        record.save()

        # connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        # channel    = connection.channel()
        
        # channel.queue_bind(exchange=str(organization.id),
        # queue=str(user.id), routing_key=str(record.id))
        # connection.close()

        return redirect('timeline_app:list-timelines')

class DeleteTimeline(GuardianView):
    def get(self, request,  timeline_id):
        timeline = models.Timeline.objects.get(id = timeline_id)
        user     = timeline_app.models.User.objects.get(id=self.user_id)
        event    = models.EDeleteTimeline.objects.create(organization=user.default,
        timeline_name=timeline.name, user=user)

        event.users.add(*timeline.users.all())
        timeline.delete()
            
        return redirect('timeline_app:list-timelines')

class UnbindTimelineUser(GuardianView):
    def get(self, request, timeline_id, user_id):
        user = models.User.objects.get(id=user_id)
        timeline = models.Timeline.objects.get(id=timeline_id)
        timeline.users.remove(user)
        timeline.save()
        me = models.User.objects.get(id=self.user_id)

        event    = models.EUnbindTimelineUser.objects.create(organization=me.default,
        timeline=timeline, user=me, peer=user)

        event.users.add(*timeline.users.all())

        return HttpResponse(status=200)

class UpdateTimeline(GuardianView):
    def get(self, request, timeline_id):
        timeline = models.Timeline.objects.get(id=timeline_id)
        return render(request, 'timeline_app/update-timeline.html',
        {'timeline': timeline, 'form': forms.TimelineForm(instance=timeline)})

    def post(self, request, timeline_id):
        record  = models.Timeline.objects.get(id=timeline_id)
        form    = forms.TimelineForm(request.POST, instance=record)

        if not form.is_valid():
            return render(request, 'timeline_app/update-timeline.html',
                                    {'timeline': record, 'form': form})
        form.save()

        user  = timeline_app.models.User.objects.get(id=self.user_id)
        event = models.EUpdateTimeline.objects.create(organization=user.default,
        timeline=record, user=user)

        event.users.add(*record.users.all())

        return redirect('timeline_app:list-posts', 
        timeline_id=record.id)

class PastePosts(GuardianView):
    def get(self, request, timeline_id):
        timeline = models.Timeline.objects.get(id=timeline_id)
        user     = models.User.objects.get(id=self.user_id)
        users    = timeline.users.all()

        for ind in user.clipboard.all():
            ind.post.ancestor = timeline
            ind.post.save()
            event = post_app.models.ECreatePost.objects.create(
            organization=user.default, timeline=timeline, 
            post=ind.post, user=user)
            event.users.add(*users)

        for ind in users:
            ws.client.publish(str(ind.id), 
                'Post created on: %s!' % timeline.name, 0, False)
    
        user.clipboard.clear()
        return redirect('timeline_app:list-posts', 
        timeline_id=timeline.id)

class SetupTimelineFilter(GuardianView):
    def get(self, request, organization_id):
        filter = models.TimelineFilter.objects.get(
        user__id=self.user_id, organization__id=organization_id)
        organization = timeline_app.models.Organization.objects.get(id=organization_id)

        return render(request, 'timeline_app/setup-timeline-filter.html', 
        {'form': forms.TimelineFilterForm(instance=filter), 
        'organization': organization})

    def post(self, request, organization_id):
        record = models.TimelineFilter.objects.get(
        organization__id=organization_id, user__id=self.user_id)

        form   = forms.TimelineFilterForm(request.POST, instance=record)
        organization = timeline_app.models.Organization.objects.get(id=organization_id)

        if not form.is_valid():
            return render(request, 'timeline_app/setup-timeline-filter.html',
                   {'timeline': record, 'form': form, 
                        'organization': organization}, status=400)
        form.save()
        return redirect('timeline_app:list-timelines')

class EUpdateTimeline(GuardianView):
    def get(self, request, event_id):
        event = models.EUpdateTimeline.objects.get(id=event_id)
        return render(request, 'timeline_app/e-update-timeline.html', 
        {'event':event})

class EBindTimelineUser(GuardianView):
    def get(self, request, event_id):
        event = models.EBindTimelineUser.objects.get(id=event_id)
        return render(request, 'timeline_app/e-bind-timeline-user.html', 
        {'event':event})

class EUnbindTimelineUser(GuardianView):
    def get(self, request, event_id):
        event = models.EUnbindTimelineUser.objects.get(id=event_id)
        return render(request, 'timeline_app/e-unbind-timeline-user.html', 
        {'event':event})

class EDeleteTimeline(GuardianView):
    def get(self, request, event_id):
        event = models.EDeleteTimeline.objects.get(id=event_id)
        return render(request, 'timeline_app/e-delete-timeline.html', 
        {'event':event})

class ListClipboard(GuardianView):
    def get(self, request, user_id):
        user = core_app.models.User.objects.get(id=self.user_id)
        clips = user.clipboard.all()
        return render(request, 'timeline_app/list-clipboard.html', 
        {'clips': clips, 'user': user, 'organization':user.default})


class DisabledOrganization(View):
    def get(self, request, user_id):
        user = core_app.models.User.objects.get(id=user_id)
            
        return render(request, 'timeline_app/disabled-organization.html', 
        {'user': user, 'default': user.default,
        'organizations': user.organizations})

class Index(GuardianView):
    """
    """

    def get(self, request):
        user = core_app.models.User.objects.get(id=self.user_id)
        organizations = user.organizations.exclude(id=user.default.id)
        return render(request, 'timeline_app/index.html', 
        {'user': user, 'organization': user.default,
        'organizations': organizations})


class Logout(View):
    """
    """

    def get(self, request):
        del request.session['user_id']
        return redirect('site_app:index')

class ListEvents(GuardianView):
    """
    """

    def get(self, request):
        user   = core_app.models.User.objects.get(id=self.user_id)
        events = user.events.filter(organization=user.default).order_by('-created')

        # Missing dynamic filter.
        total = user.events.filter(organization=user.default).order_by('-created')

        form = forms.FindEventForm()
        return render(request, 'timeline_app/list-events.html',
        {'user': user, 'events': events, 'form': form, 
        'total': total, 'organization': user.default})

class ListTimelines(GuardianView):
    """
    """

    def get(self, request):
        user      = core_app.models.User.objects.get(id=self.user_id)
        filter, _ = timeline_app.models.TimelineFilter.objects.get_or_create(
        user=user, organization=user.default)

        total = user.timelines.filter(organization=user.default)
        children = total.filter(Q(name__icontains=filter.pattern) | \
        Q(description__icontains=filter.pattern) if filter.status \
        else Q(organization=user.default))

        return render(request, 'timeline_app/list-timelines.html', 
        {'user': user, 'children': children, 'total': total,
        'organization':user.default, 'filter': filter})

class InviteOrganizationUser(GuardianView):
    def get(self, request, organization_id):
        organization = models.Organization.objects.get(id=organization_id)

        return render(request, 'timeline_app/invite-organization-user.html', 
        {'form': forms.BindUsersForm(), 'organization': organization})
        pass

    def post(self, request, organization_id):
        organization = models.Organization.objects.get(id=organization_id)
        form         = forms.BindUsersForm(request.POST)

        if not form.is_valid():
            return render(request, 'timeline_app/invite-organization-user.html',
                  {'form': form, 'organization': organization}, status=400)

        email = form.cleaned_data['email']

        # If the user doesn't exist
        # we send him an email invite.
        user  = core_app.models.User.objects.get(email=email)
        user.organizations.add(organization)

        return redirect('timeline_app:list-users', 
        organization_id=organization_id)

class UnbindUser(GuardianView):
    def get(self, request, organization_id, user_id):
        user = core_app.models.User.objects.get(id=user_id)

        return redirect('timeline_app:list-users', 
        organization_id=organization.id)

class CheckEvent(GuardianView):
    def get(self, request, user_id):
        user = core_app.models.User.objects.get(
        id=self.user_id)

        try:
            event = user.events.latest('id')
        except Exception:
            return HttpResponse(status=400)
        return HttpResponse(str(event.id), status=200)

class SeenEvent(GuardianView):
    def get(self, request, event_id):
        user  = core_app.models.User.objects.get(id=self.user_id)
        event = models.Event.objects.get(id=event_id)
        event.users.remove(user)
        event.save()
        return redirect('timeline_app:list-events')


class BindTimelineUser(GuardianView):
    def get(self, request, timeline_id, user_id):
        user = core_app.models.User.objects.get(id=user_id)
        timeline = timeline_app.models.Timeline.objects.get(id=timeline_id)

        timeline.users.add(user)
        timeline.save()

        me = models.User.objects.get(id=self.user_id)

        event    = models.EBindTimelineUser.objects.create(organization=me.default,
        timeline=timeline, user=me, peer=user)

        event.users.add(*timeline.users.all())

        return HttpResponse(status=200)

class ManageUserTimelines(GuardianView):
    def get(self, request, user_id):
        me = core_app.models.User.objects.get(id=self.user_id)
        user = core_app.models.User.objects.get(id=user_id)

        timelines = me.timelines.filter(organization=me.default)
        excluded = timelines.exclude(users=user)
        included = timelines.filter(users=user)

        return render(request, 'timeline_app/manage-user-timelines.html', 
        {'user': user, 'included': included, 'excluded': excluded,
        'me': me, 'organization': me.default,'form':forms.BindTimelinesForm()})

    def post(self, request, user_id):
        user = core_app.models.User.objects.get(id=user_id)
        form = forms.BindTimelinesForm(request.POST)

        me = core_app.models.User.objects.get(id=self.user_id)
        timelines = me.timelines.filter(organization=me.default)

        if not form.is_valid():
            return render(request, 'timeline_app/manage-user-timelines.html', 
                {'user': user, 'included': included, 'excluded': excluded,
                    'me': me, 'organization': me.default, 
                        'form':forms.BindTimelinesForm()}, status=400)

        timelines = timelines.filter(
        name__contains=form.cleaned_data['name'])

        # timeline.users.add(user)
        # timeline.save()

        # return redirect('timeline_app:list-user-tags', 
        # user_id=user.id)
        excluded = timelines.exclude(users=user)
        included = timelines.filter(users=user)

        return render(request, 'timeline_app/manage-user-timelines.html', 
        {'user': user, 'included': included, 'excluded': excluded,
        'me': me, 'organization': me.default,'form':forms.BindTimelinesForm()})

class CreateTag(GuardianView):
    def get(self, request):
        user     = core_app.models.User.objects.get(id=self.user_id)
        form = forms.TagForm()

        return render(request, 'timeline_app/create-tag.html', 
        {'form':form})

    def post(self, request):
        user = core_app.models.User.objects.get(id=self.user_id)
        form = forms.TagForm(request.POST)

        if not form.is_valid():
            return render(request, 'timeline_app/create-tag.html',
                        {'form': form, 'user': user}, status=400)
        record       = form.save(commit=False)
        record.organization = user.default
        record.save()
        return redirect('timeline_app:list-tags')

class ListTags(GuardianView):
    def get(self, request):
        user      = core_app.models.User.objects.get(id=self.user_id)
        tags = models.Tag.objects.filter(organization=user.default)
        form = forms.FindTagForm()

        return render(request, 'timeline_app/list-tags.html', 
        {'tags': tags, 'form': form, 'user': user, 
        'organization': user.default})

class BindTag(GuardianView):
    def get(self, request, user_id):
        user = core_app.models.User.objects.get(id=user_id)
        return render(request, 'timeline_app/bind-tag.html', 
        {'user': user, 'form':forms.BindTagForm()})

    def post(self, request, user_id):
        user = core_app.models.User.objects.get(id=user_id)
        form = forms.BindTagForm(request.POST)

        if not form.is_valid():
            return render(request, 'timeline_app/bind-tag.html',
                  {'form': form, 'user': user}, status=400)

        me = core_app.models.User.objects.get(id=self.user_id)
        tag = models.Tag.objects.get(
        organization=me.default, name=form.cleaned_data['name'])
        user.tags.add(tag)

        return redirect('core_app:list-user-tags', 
        user_id=user.id)

class UnbindUserTag(GuardianView):
    def get(self, request, tag_id, user_id):
        user = core_app.models.User.objects.get(id=user_id)
        tag = models.Tag.objects.get(id=tag_id)
        tag.users.remove(user)
        tag.save()

        return redirect('core_app:list-user-tags', 
        user_id=user_id)


class ManageTimelineUsers(GuardianView):
    def get(self, request, timeline_id):
        me = core_app.models.User.objects.get(id=self.user_id)
        timeline = models.Timeline.objects.get(id=timeline_id)

        included = timeline.users.all()
        excluded = core_app.models.User.objects.exclude(timelines=timeline)

        return render(request, 'timeline_app/manage-timeline-users.html', 
        {'included': included, 'excluded': excluded, 'timeline': timeline,
        'me': me, 'organization': me.default,'form':forms.UserSearchForm()})

    def post(self, request, timeline_id):
        form = forms.UserSearchForm(request.POST)

        me = core_app.models.User.objects.get(id=self.user_id)
        timeline = models.Timeline.objects.get(id=timeline_id)
        included = timeline.users.all()
        excluded = core_app.models.User.objects.exclude(timelines=timeline)

        if not form.is_valid():
            return render(request, 'timeline_app/manage-timeline-users.html', 
                {'included': included, 'excluded': excluded,
                    'me': me, 'organization': me.default, 'timeline': timeline,
                        'form':forms.UserSearchForm()}, status=400)

        included = included.filter(
        name__contains=form.cleaned_data['name'])

        excluded = excluded.filter(
        name__contains=form.cleaned_data['name'])

        return render(request, 'timeline_app/manage-timeline-users.html', 
        {'included': included, 'excluded': excluded, 'timeline': timeline,
        'me': me, 'organization': me.default,'form':forms.UserSearchForm()})







