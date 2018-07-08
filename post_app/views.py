from post_app.models import EUnbindTagPost, ECreatePost, EUpdatePost, \
PostFileWrapper, EDeletePost, EAssignPost, EBindTagPost, EUnassignPost, \
PostFilter, GlobalPostFilter, ECutPost, EArchivePost, ECopyPost, \
EUnarchivePost
from django.db.models import Q, F, Exists, OuterRef, Count, Sum
from core_app.models import Clipboard, Tag, User, Event
from django.db.models.functions import Concat
from django.shortcuts import render, redirect
from core_app.views import GuardianView
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.core.mail import send_mail
from django.http import HttpResponse
from list_app.models import List
from group_app.models import Group, EPastePost
from django.conf import settings
from jscroll.wrappers import JScroll
from card_app.models import Card
from django.db import transaction
from card_app.forms import CardForm, ListSearchform
from functools import reduce
from re import split
from . import forms
from . import models
import operator

import json

class Post(GuardianView):
    """
    This view is supposed to be performed only if the user
    belongs to the group or if he is a worker of the post.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        boardpins    = self.me.boardpin_set.filter(organization=self.me.default)
        listpins     = self.me.listpin_set.filter(organization=self.me.default)
        cardpins     = self.me.cardpin_set.filter(organization=self.me.default)
        grouppins = self.me.grouppin_set.filter(
        organization=self.me.default)

        return render(request, 'post_app/post.html', 
        {'post':post, 'boardpins': boardpins, 'listpins': listpins, 
        'cardpins': cardpins, 'tags': post.tags.all(), 
        'grouppins': grouppins, 'user': self.me, })

class PostLink(GuardianView):
    """
    This view worksk alike like Post in terms of permissions.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        organizations = self.me.organizations.exclude(id=self.me.default.id)

        boardpins = self.me.boardpin_set.filter(organization=self.me.default)
        listpins = self.me.listpin_set.filter(organization=self.me.default)
        cardpins = self.me.cardpin_set.filter(organization=self.me.default)
        grouppins = self.me.grouppin_set.filter(organization=self.me.default)

        return render(request, 'post_app/post-link.html', 
        {'post':post, 'boardpins': boardpins, 'listpins': listpins, 
        'grouppins': grouppins, 'cardpins': cardpins, 'user': self.me, 
        'default': self.me.default, 'organization': self.me.default, 
        'organizations': organizations, 'settings': settings})

class CreatePost(GuardianView):
    """
    The logged user can create a post on the group just if his default organization
    contains the group and he belongs to the group.
    """

    def get(self, request, ancestor_id):
        ancestor   = self.me.groups.get(id=ancestor_id, 
        organization=self.me.default)

        form = forms.PostForm()

        return render(request, 'post_app/create-post.html', 
        {'form':form, 'ancestor':ancestor})

    def post(self, request, ancestor_id):
        ancestor   = self.me.groups.get(id=ancestor_id, 
        organization=self.me.default)

        form = forms.PostForm(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, 'post_app/create-post.html',
                        {'form': form, 'ancestor': ancestor}, status=400)

        post          = form.save(commit=False)
        post.user     = self.me
        post.ancestor = ancestor
        post.save()

        event = ECreatePost.objects.create(organization=self.me.default,
        group=ancestor, post=post, user=self.me)

        users = ancestor.users.all()
        event.dispatch(*users)

        return redirect('group_app:list-posts', 
        group_id=ancestor_id)

class UpdatePost(GuardianView):
    """
    The post can be updated by everyone who belongs to the 
    group or is a worker of the post. 

    It also makes sure the user who performs this view has set as 
    default the organization whose post belongs to.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        return render(request, 'post_app/update-post.html',
        {'post': post, 'form': forms.PostForm(instance=post)})

    def post(self, request, post_id):
        record = models.Post.locate(self.me, self.me.default, post_id)
        form = forms.PostForm(request.POST, request.FILES, instance=record)

        if not form.is_valid():
            return render(request, 'post_app/update-post.html',
                   {'post': record, 'form': form}, status=400)
        record.save()

        event = EUpdatePost.objects.create(organization=self.me.default,
        group=record.ancestor, post=record, user=self.me)

        event.dispatch(*record.ancestor.users.all())

        # Notify workers of the event, in case the post
        # is on a group whose worker is not on.
        event.dispatch(*record.workers.all())

        return redirect('post_app:refresh-post', 
        post_id=record.id)


class AttachFile(GuardianView):
    """
    It follows the same permission scheme for update-post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        attachments = post.postfilewrapper_set.all()
        form = forms.PostFileWrapperForm()
        return render(request, 'post_app/attach-file.html', 
        {'post':post, 'form': form, 'attachments': attachments})

    def post(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        attachments = post.postfilewrapper_set.all()
        form = forms.PostFileWrapperForm(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, 'post_app/attach-file.html', 
                {'post':post, 'form': form, 'attachments': attachments})
        record = form.save(commit = False)
        record.post = post
        form.save()

        event = models.EAttachPostFile.objects.create(
        organization=self.me.default, filewrapper=record, 
        post=post, user=self.me)

        event.dispatch(*post.ancestor.users.all())
        event.save()

        return self.get(request, post_id)

class DetachFile(GuardianView):
    """
    The same permission scheme for attach-file view.
    """

    def get(self, request, filewrapper_id):
        filewrapper = PostFileWrapper.objects.filter(
        Q(post__ancestor__users=self.me) | Q(post__workers=self.me),
        id=filewrapper_id, post__ancestor__organization=self.me.default)
        filewrapper = filewrapper.distinct().first()
        attachments = filewrapper.post.postfilewrapper_set.all()

        form = forms.PostFileWrapperForm()

        event = models.EDettachPostFile.objects.create(
        organization=self.me.default, filename=filewrapper.file.name, 
        post=filewrapper.post, user=self.me)

        filewrapper.delete()

        event.dispatch(*filewrapper.post.ancestor.users.all())
        event.save()

        return render(request, 'post_app/attach-file.html', 
        {'post':filewrapper.post, 'form': form, 'attachments': attachments})

class DeletePost(GuardianView):
    """
    The same permission scheme for update-post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        event = EDeletePost.objects.create(organization=self.me.default,
        group=post.ancestor, post_label=post.label, user=self.me)
        users = post.ancestor.users.all()
        event.dispatch(*users)

        ancestor = post.ancestor
        post.delete()

        return redirect('group_app:list-posts', 
        group_id=ancestor.id)

class PostWorkerInformation(GuardianView):
    """
    Same permission scheme as in Post view.
    """

    def get(self, request, peer_id, post_id):
        event = EAssignPost.objects.filter(
        Q(post__ancestor__users=self.me) | Q(post__workers=self.me),
        post_id=post_id, post__ancestor__organization=self.me.default,
        peer__id=peer_id).last()

        active_posts = event.peer.assignments.filter(done=False)
        done_posts = event.peer.assignments.filter(done=True)

        active_cards = event.peer.tasks.filter(done=False)
        done_cards = event.peer.tasks.filter(done=True)

        active_tasks = active_posts.count() + active_cards.count()
        done_tasks = done_posts.count() + done_cards.count()

        return render(request, 
        'post_app/post-worker-information.html',  
        {'peer': event.peer, 'active_tasks': active_tasks, 
         'post': event.post,  'done_tasks': done_tasks,
        'created': event.created, 'user':event.user})

class PostTagInformation(GuardianView):
    """
    Same permission scheme as PostWorkerInformation.
    """

    def get(self, request, tag_id, post_id):
        event = EBindTagPost.objects.filter(
        Q(post__ancestor__users=self.me) | Q(post__workers=self.me),
        post_id=post_id, post__ancestor__organization=self.me.default,
        tag__id=tag_id).last()

        return render(request, 'post_app/post-tag-information.html', 
        {'user': event.user, 'created': event.created, 'tag':event.tag})

class UnassignPostUser(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id, user_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        user = User.objects.get(id=user_id)

        event = EUnassignPost.objects.create(
        organization=self.me.default, ancestor=post.ancestor, 
        post=post, user=self.me, peer=user)

        event.dispatch(*post.ancestor.users.all())
        
        # As posts can be assigned to users off the group.
        # We make sure them get the evvent.
        event.dispatch(*post.workers.all())
        event.save()

        post.workers.remove(user)
        post.save()

        return HttpResponse(status=200)

class AssignPostUser(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id, user_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        user = User.objects.get(id=user_id)

        post.workers.add(user)
        post.save()

        event = EAssignPost.objects.create(
        organization=self.me.default, ancestor=post.ancestor, 
        post=post, user=self.me, peer=user)

        event.dispatch(*post.ancestor.users.all())
        event.dispatch(*post.workers.all())
        event.save()

        return HttpResponse(status=200)

class ManagePostWorkers(GuardianView):
    """
    Same as in post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        included = post.workers.all()
        excluded = self.me.default.users.exclude(assignments=post)
        total    = included.count() + excluded.count()

        return render(request, 'post_app/manage-post-workers.html', 
        {'included': included, 'excluded': excluded, 'post': post,
        'count': total, 'total': total, 'me': self.me, 
        'form':forms.UserSearchForm()})

    def post(self, request, post_id):
        sqlike = User.from_sqlike()
        form = forms.UserSearchForm(request.POST, sqlike=sqlike)

        post = models.Post.locate(self.me, self.me.default, post_id)

        included = post.workers.all()
        excluded = self.me.default.users.exclude(assignments=post)
        total    = included.count() + excluded.count()

        if not form.is_valid():
            return render(request, 'post_app/manage-post-workers.html',  
                {'me': self.me, 'total': total, 'count': 0, 'post': post, 
                    'form':form}, status=400)

        included = sqlike.run(included)
        excluded = sqlike.run(excluded)
        count = included.count() + excluded.count()

        return render(request, 'post_app/manage-post-workers.html', 
        {'included': included, 'excluded': excluded, 'post': post,
        'me': self.me, 'form':form, 'total': total, 'count': count,})

class SetupPostFilter(GuardianView):
    """
    Makes sure the user can have a filter only if he belongs
    to the group in fact. 

    Notice that when the user is removed from the group the 
    filter remains in the db.
    """

    def get(self, request, group_id):
        group = self.me.groups.get(id=group_id, 
        organization=self.me.default)

        filter = PostFilter.objects.get(
        user__id=self.user_id, group__id=group_id)


        return render(request, 'post_app/setup-post-filter.html', 
        {'form': forms.PostFilterForm(instance=filter), 
        'group': group})

    def post(self, request, group_id):
        record = PostFilter.objects.get(
        group__id=group_id, user__id=self.user_id)
        sqlike = models.Post.from_sqlike()

        form     = forms.PostFilterForm(request.POST, sqlike=sqlike, instance=record)
        group = self.me.groups.get(id=group_id, 
        organization=self.me.default)

        if not form.is_valid():
            return render(request, 'post_app/setup-post-filter.html',
                   {'group': record, 'form': form}, status=400)
        form.save()
        return redirect('group_app:list-posts', group_id=group.id)

class Find(GuardianView):
    """
    This view is already secured for default due to the way of how
    it is implemented.
    """

    def get(self, request):
        filter, _ = GlobalPostFilter.objects.get_or_create(
        user=self.me, organization=self.me.default)
        form   = forms.GlobalPostFilterForm(instance=filter)
        posts  = models.Post.get_allowed_posts(self.me)
        total  = posts.count()

        sqlike = models.Post.from_sqlike()
        posts  = filter.get_partial(posts)

        sqlike.feed(filter.pattern)

        posts = sqlike.run(posts)
        count = posts.count()

        posts = posts.only('done', 'label', 'id').order_by('id')
        elems = JScroll(self.me.id, 'post_app/find-scroll.html', posts)

        return render(request, 'post_app/find.html', 
        {'form': form, 'elems':  elems.as_div(), 'total': total, 'count': count})

    def post(self, request):
        filter, _ = GlobalPostFilter.objects.get_or_create(
        user=self.me, organization=self.me.default)

        sqlike = models.Post.from_sqlike()
        form  = forms.GlobalPostFilterForm(request.POST, sqlike=sqlike, instance=filter)

        posts = models.Post.get_allowed_posts(self.me)
        total = posts.count()

        if not form.is_valid():
            return render(request, 'post_app/find.html', 
                {'form': form, 'total': total, 'count': 0}, status=400)
        form.save()

        posts = filter.get_partial(posts)
        posts = sqlike.run(posts)

        count = posts.count()

        posts = posts.only('done', 'label', 'id').order_by('id')
        elems = JScroll(self.me.id, 'post_app/find-scroll.html', posts)

        return render(request, 'post_app/find.html', 
        {'form': form, 'elems':  elems.as_div(), 'total': total, 'count': count})

class CutPost(GuardianView):
    """
    Same as in update-post view permission scheme.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        group = post.ancestor

        post.ancestor = None
        post.save()

        clipboard, _ = Clipboard.objects.get_or_create(
        user=self.me, organization=self.me.default)

        clipboard.posts.add(post)

        event = ECutPost.objects.create(organization=self.me.default,
        group=group, post=post, user=self.me)
        users = group.users.all()
        event.dispatch(*users)

        return redirect('group_app:list-posts', 
        group_id=group.id)

class CopyPost(GuardianView):
    """
    Same as in CutPost view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        copy         = post.duplicate()
        clipboard, _ = Clipboard.objects.get_or_create(
        user=self.me, organization=self.me.default)
        clipboard.posts.add(copy)

        event = ECopyPost.objects.create(organization=self.me.default,
        group=post.ancestor, post=post, user=self.me)
        users = post.ancestor.users.all()
        event.dispatch(*users)

        return redirect('group_app:list-posts', 
        group_id=post.ancestor.id)

class Done(GuardianView):
    """
    Same as in copy-post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        post.done = True
        post.save()

        # posts in the clipboard cant be archived.
        event = EArchivePost.objects.create(organization=self.me.default,
        group=post.ancestor, post=post, user=self.me)

        users = post.ancestor.users.all()
        event.dispatch(*users)

        return redirect('post_app:refresh-post', 
        post_id=post.id)

class ManagePostTags(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        included = post.tags.all()
        excluded = self.me.default.tags.exclude(posts=post)
        total = included.count() + excluded.count()

        return render(request, 'post_app/manage-post-tags.html', 
        {'included': included, 'excluded': excluded, 'post': post,
        'organization': self.me.default,'form':forms.TagSearchForm(), 
        'total': total, 'count': total})

    def post(self, request, post_id):
        sqlike = Tag.from_sqlike()
        form = forms.TagSearchForm(request.POST, sqlike=sqlike)

        post = models.Post.locate(self.me, self.me.default, post_id)

        included = post.tags.all()
        excluded = self.me.default.tags.exclude(posts=post)
        total = included.count() + excluded.count()

        if not form.is_valid():
            return render(request, 'post_app/manage-post-tags.html', 
                {'total': total, 'organization': self.me.default, 
                    'post': post, 'form':form, 'count': 0}, status=400)

        included = sqlike.run(included)
        excluded = sqlike.run(excluded)
        count = included.count() + excluded.count()

        return render(request, 'post_app/manage-post-tags.html', 
        {'included': included, 'excluded': excluded, 'post': post, 
        'total': total, 'count': count, 'me': self.me, 'form':form, 
        'organization': self.me.default, })

class UnbindPostTag(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id, tag_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        tag = Tag.objects.get(id=tag_id)
        post.tags.remove(tag)
        post.save()

        event = EUnbindTagPost.objects.create(
        organization=self.me.default, ancestor=post.ancestor, 
        post=post, tag=tag, user=self.me)
        event.dispatch(*post.ancestor.users.all())
        event.save()

        return HttpResponse(status=200)

class BindPostTag(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id, tag_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        tag = Tag.objects.get(id=tag_id)
        post.tags.add(tag)
        post.save()

        event = EBindTagPost.objects.create(
        organization=self.me.default, ancestor=post.ancestor, 
        post=post, tag=tag, user=self.me)
        event.dispatch(*post.ancestor.users.all())
        event.save()

        return HttpResponse(status=200)

class CancelPostCreation(GuardianView):
    """
    Deprecated.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        post.delete()

        return HttpResponse(status=200)

class Undo(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        post.done = False
        post.save()

        event = EUnarchivePost.objects.create(organization=self.me.default,
        group=post.ancestor, post=post, user=self.me)

        users = post.ancestor.users.all()
        event.dispatch(*users)

        return redirect('post_app:refresh-post', 
        post_id=post.id)


class RequestPostAttention(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, peer_id, post_id):
        peer = User.objects.get(id=peer_id, organizations=self.me.default)
        post = models.Post.locate(self.me, self.me.default, post_id)

        form = forms.PostAttentionForm()
        return render(request, 'post_app/request-post-attention.html', 
        {'peer': peer,  'post': post, 'form': form})

    def post(self, request, peer_id, post_id):
        peer = User.objects.get(id=peer_id, organizations=self.me.default)
        post = models.Post.locate(self.me, self.me.default, post_id)

        form = forms.PostAttentionForm(request.POST)

        if not form.is_valid():
            return render(request, 'post_app/request-post-attention.html', 
                    {'peer': peer, 'post': post, 'form': form})    

        url  = reverse('post_app:post-link', 
            kwargs={'post_id': post.id})

        url = '%s%s' % (settings.LOCAL_ADDR, url)
        msg = '%s (%s) has requested your attention on\n%s\n\n%s' % (
        self.me.name, self.me.email, url, form.cleaned_data['message'])

        send_mail('%s %s' % (self.me.default.name, 
        self.me.name), msg, self.me.email, [peer.email], fail_silently=False)

        return redirect('post_app:post-worker-information', 
        peer_id=peer.id, post_id=post.id)

class AlertPostWorkers(GuardianView):
    """
    Same as in update-post view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        form = forms.AlertPostWorkersForm()
        return render(request, 'post_app/alert-post-workers.html', 
        {'post': post, 'form': form, 'user': self.me})

    def post(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        form = forms.AlertPostWorkersForm(request.POST)

        if not form.is_valid():
            return render(request,'post_app/alert-post-workers.html', 
                    {'user': self.me, 'post': post, 'form': form})    

        url  = reverse('post_app:post-link', 
        kwargs={'post_id': post.id})

        url = '%s%s' % (settings.LOCAL_ADDR, url)
        msg = '%s (%s) has alerted you on\n%s\n\n%s' % (
        self.me.name, self.me.email, url, form.cleaned_data['message'])

        for ind in post.workers.values_list('email'):
            send_mail('%s %s' % (self.me.default.name, 
                self.me.name), msg, self.me.email, 
                    [ind[0]], fail_silently=False)

        return render(request, 'post_app/alert-post-workers-sent.html', {})

class ConfirmPostDeletion(GuardianView):
    """
    The user is supposed to view this dialog only if he
    belongs to the group post or is a worker of the post.
    
    It enforces his default organization contains the post's group
    as well.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        return render(request, 'post_app/confirm-post-deletion.html', 
        {'post': post})


class PullCardContent(GuardianView):
    """
    The user has to be related to the post either by
    belonging to the group/being a worker. 

    The user has to be in the list's board that the 
    post is forked into as well.
    """

    def get(self, request, ancestor_id, post_id):
        # Make sure i belong to the board and the board belongs
        # to my default organization.
        ancestor = List.objects.get(id=ancestor_id, 
        ancestor__organization=self.me.default, 
        ancestor__members=self.me)

        post = models.Post.locate(self.me, self.me.default, post_id)
        form = CardForm(initial={'label': post.label, 'data': post.data})

        return render(request, 'post_app/create-fork.html', 
        {'form':form, 'post': post, 'ancestor': ancestor})

class CreatePostFork(GuardianView):
    """
    """

    def get(self, request, ancestor_id, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        ancestor = List.objects.get(id=ancestor_id)
        form = CardForm()

        return render(request, 'post_app/create-fork.html', 
        {'form':form, 'post': post, 'ancestor': ancestor})

    def post(self, request, ancestor_id, post_id):
        ancestor = List.objects.get(id=ancestor_id, 
        ancestor__organization=self.me.default, 
        ancestor__members=self.me)

        post = models.Post.locate(self.me, self.me.default, post_id)
        form = CardForm(request.POST)

        if not form.is_valid():
            return render(request, 'post_app/create-fork.html', 
                {'form':form, 'ancestor': ancestor, 'post': post}, status=400)

        fork             = form.save(commit=False)
        fork.owner       = self.me
        fork.ancestor    = ancestor
        fork.parent_post = post
        fork.save()

        # # path = post.path.all()
        # fork.parent_post = post
        # # fork.path.add(*path, post)
        # fork.save()

        event = models.ECreatePostFork.objects.create(organization=self.me.default,
        group=post.ancestor, list=fork.ancestor, post=post, card=fork, 
        board=fork.ancestor.ancestor, user=self.me)

        # The group users and the board users get the event.
        event.dispatch(*post.ancestor.users.all())
        event.dispatch(*fork.ancestor.ancestor.members.all())

        return redirect('card_app:view-data', card_id=fork.id)

class SelectForkList(GuardianView):
    """
    The user is supposed to view the dialog just if matches
    the same permission criterea in create-fork view view.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        form = ListSearchform()

        boards = self.me.boards.filter(organization=self.me.default)
        lists  = List.objects.filter(ancestor__in=boards)

        return render(request, 'post_app/select-fork-list.html', 
        {'form':form, 'post': post, 'elems': lists})

    def post(self, request, post_id):
        sqlike = List.from_sqlike()
        form = forms.ListSearchform(request.POST, sqlike=sqlike)

        post = models.Post.locate(self.me, self.me.default, post_id)

        if not form.is_valid():
            return render(request, 'post_app/select-fork-list.html', 
                  {'form':form, 'post': post})

        boards = self.me.boards.filter(organization=self.me.default)
        lists  = List.objects.filter(ancestor__in=boards)
        lists  = sqlike.run(lists)

        return render(request, 'post_app/select-fork-list.html', 
        {'form':form, 'post': post, 'elems': lists})

class PostEvents(GuardianView):
    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        query = Q(eunbindtagpost__post__id= post.id) | \
        Q(ecreatepost__post__id=post.id) | Q(eupdatepost__post__id= post.id) | \
        Q(eassignpost__post__id=post.id) | Q(ebindtagpost__post__id= post.id) |\
        Q(eunassignpost__post__id= post.id)| \
        Q(ecutpost__post__id = post.id) | Q(earchivepost__post__id=post.id) |\
        Q(ecopypost__post__id=post.id) | Q(ecreatepostfork__post__id=post.id) | \
        Q(epastepost__posts=post.id) | Q(ecreatesnippet__child__id=post.id) | \
        Q(eupdatesnippet__child__id=post.id) | Q(edeletesnippet__child__id=post.id) |\
        Q(eattachsnippetfile__snippet__post__id=post.id) | \
        Q(eattachpostfile__post__id=post.id) | \
        Q(edettachpostfile__post__id=post.id) | \
        Q(edettachsnippetfile__snippet__post__id=post.id)|\
        Q(esetpostpriorityup__post0__id=post.id)|\
        Q(esetpostprioritydown__post0__id=post.id)|\
        Q(esetpostpriorityup__post1__id=post.id)|\
        Q(esetpostprioritydown__post1__id=post.id)|\
        Q(eremovepostfork__post=post.id)|\
        Q(eunarchivepost__post__id=post.id)
        events = Event.objects.filter(query).order_by('-created').values('html')

        return render(request, 'post_app/post-events.html', 
        {'post': post, 'elems': events})


class PinPost(GuardianView):
    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)

        pin   = PostPin.objects.create(user=self.me, 
        organization=self.me.default, post=post)
        return redirect('board_app:list-pins')

class Unpin(GuardianView):
    def get(self, request, pin_id):
        pin = self.me.postpin_set.get(id=pin_id)
        pin.delete()
        return redirect('board_app:list-pins')

class RefreshPost(GuardianView):
    """
    Used to update a post view after changing its data.
    """

    def get(self, request, post_id):
        post = models.Post.locate(self.me, self.me.default, post_id)
        # boardpins = user.boardpin_set.filter(organization=user.default)
        # listpins = user.listpin_set.filter(organization=user.default)
        # cardpins = user.cardpin_set.filter(organization=user.default)
        # grouppins = user.grouppin_set.filter(organization=user.default)

        return render(request, 'post_app/post-data.html', 
        {'post':post, 'tags': post.tags.all(), 'user': self.me, })


class PostPriority(GuardianView):
    def get(self, request, post_id):
        post  = models.Post.locate(self.me, self.me.default, post_id)
        posts = post.ancestor.posts.filter(done=False)
        posts = posts.order_by('-priority')
        total = posts.count()

        return render(request, 'post_app/post-priority.html', 
        {'post': post, 'total': total, 'count': total, 'me': self.me,
        'posts': posts, 'form': forms.PostPriorityForm()})

    def post(self, request, post_id):
        sqlike = models.Post.from_sqlike()
        post   = models.Post.locate(self.me, self.me.default, post_id)
        posts  = post.ancestor.posts.filter(done=False)
        total  = posts.count()
        form   = forms.PostPriorityForm(request.POST, sqlike=sqlike)

        if not form.is_valid():
            return render(request, 'post_app/post-priority.html', 
                {'me': self.me, 'organization': self.me.default, 'post': post,
                     'total': total, 'count': 0, 'form':form}, status=400)

        posts = sqlike.run(posts)
        posts = posts.order_by('-priority')

        count = posts.count()

        return render(request, 'post_app/post-priority.html', 
        {'post': post, 'total': total, 'count': count, 'me': self.me,
        'posts': posts, 'form': form})

class SetPostPriorityUp(GuardianView):
    @transaction.atomic
    def get(self, request, post0_id, post1_id):
        post0  = models.Post.locate(self.me, self.me.default, post0_id)
        post1  = models.Post.locate(self.me, self.me.default, post1_id)
        dir    = -1 if post0.priority < post1.priority else 1
        flag   = 0 if post0.priority <= post1.priority else 1

        q0     = Q(priority__lte=post1.priority, priority__gt=post0.priority)
        q1     = Q(priority__gt=post1.priority, priority__lt=post0.priority)
        query  = q0 if post0.priority < post1.priority else q1
        posts  = post0.ancestor.posts.filter(query)

        posts.update(priority=F('priority') + dir)
        post0.priority = post1.priority + flag
        post0.save()

        event = models.ESetPostPriorityUp.objects.create(organization=self.me.default,
        ancestor=post0.ancestor, post0=post0, post1=post1, user=self.me)
        event.dispatch(*post0.ancestor.users.all())
        print('Priority', [[ind.label, ind.priority] for ind in post0.ancestor.posts.all().order_by('-priority')])

        return redirect('group_app:list-posts', group_id=post0.ancestor.id)

class SetPostPriorityDown(GuardianView):
    @transaction.atomic
    def get(self, request, post0_id, post1_id):
        post0  = models.Post.locate(self.me, self.me.default, post0_id)
        post1  = models.Post.locate(self.me, self.me.default, post1_id)
        dir    = -1 if post0.priority < post1.priority else 1
        flag   = -1 if post0.priority < post1.priority else 0

        q0     = Q(priority__lt=post1.priority, priority__gt=post0.priority)
        q1     = Q(priority__gte=post1.priority, priority__lt=post0.priority)
        query  =  q0 if post0.priority < post1.priority else q1
        posts  = post0.ancestor.posts.filter(query)

        posts.update(priority=F('priority') + dir)
        post0.priority = post1.priority + flag
        post0.save()

        event = models.ESetPostPriorityDown.objects.create(organization=self.me.default,
        ancestor=post0.ancestor, post0=post0, post1=post1, user=self.me)
        event.dispatch(*post0.ancestor.users.all())
        print('Priority', [[ind.label, ind.priority] for ind in post0.ancestor.posts.all().order_by('-priority')])

        return redirect('group_app:list-posts', group_id=post0.ancestor.id)

class PostFileDownload(GuardianView):
    def get(self, request, filewrapper_id):
        filewrapper = PostFileWrapper.objects.filter(
        Q(post__ancestor__users=self.me) | Q(post__workers=self.me),
        id=filewrapper_id, post__ancestor__organization=self.me.default)
        filewrapper = filewrapper.distinct().first()

        return redirect(filewrapper.file.url)









