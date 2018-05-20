# Models for Snippet post type.

from django.db import models
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse
from markdown.extensions.tables import TableExtension
from mdx_gfm import GithubFlavoredMarkdownExtension
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from markdown import markdown
from board_app.models import Event

class SnippetMixin(object):
    def save(self, *args, **kwargs):
        self.html = markdown(self.data,
        extensions=[TableExtension(), GithubFlavoredMarkdownExtension()], safe_mode=True,  
        enable_attributes=False)

        super(SnippetMixin, self).save(*args, **kwargs)

    def get_absolute_url(self):
        url = reverse('post_comment_app:comment', 
        kwargs={'comment_id': self.id})
        return url

    def get_link_url(self):
        return reverse('snippet_app:snippet-link', 
                    kwargs={'snippet_id': self.id})

    def __str__(self):
        return self.data

class SnippetFileWrapperMixin(object):
    def duplicate(self, post=None):
        wrapper       = SnippetFileWrapper.objects.get(id=self.id)
        wrapper.pk    = None
        wrapper.post  = post
        wrapper.save()
        return wrapper

class SnippetFileWrapper(SnippetFileWrapperMixin, models.Model):
    """
    """

    snippet = models.ForeignKey('Snippet', null=True, 
    on_delete=models.CASCADE, blank=True)

    file = models.FileField(
    verbose_name='', help_text='')

class Snippet(SnippetMixin, models.Model):
    post = models.ForeignKey('post_app.Post', 
    null=True, related_name='snippets', blank=True)

    owner = models.ForeignKey('core_app.User', 
    null=True, blank=True)

    title = models.CharField(null=True, blank=False, 
    default='', verbose_name=_("Title"), 
    max_length=626)

    data = models.TextField(null=True, 
    blank=True, verbose_name=_("Data"), 
    help_text='Markdown content.', default='')

    created = models.DateTimeField(
    auto_now=True, null=True)

    html = models.TextField(null=True, blank=True)

class ECreateSnippet(Event):
    child = models.ForeignKey('post_app.Post', blank=True)
    snippet = models.ForeignKey('Snippet', blank=True)
    html_template = 'snippet_app/e-create-snippet.html'

    def __str__(self):
        return self.user.name

class EDeleteSnippet(Event):
    child = models.ForeignKey('post_app.Post', 
    blank=True)

    snippet = models.CharField(null=True, blank=False, 
    max_length=626)

    html_template = 'snippet_app/e-delete-snippet.html'

    def __str__(self):
        return self.user.name

class EUpdateSnippet(Event):
    child = models.ForeignKey('post_app.Post', 
    blank=True)

    snippet = models.ForeignKey('Snippet', 
    blank=True)

    html_template = 'snippet_app/e-update-snippet.html'

    def __str__(self):
        return self.user.name

# Signals.
@receiver(pre_delete, sender=SnippetFileWrapper)
def delete_filewrapper(sender, instance, **kwargs):
    instance.file.delete(save=False)




