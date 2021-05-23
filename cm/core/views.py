from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from django.conf import settings

from django.contrib.auth.decorators import login_required



class IndexTemplateViews(LoginRequiredMixin,TemplateView):
    def get_template_names(self):
#        request = self.context.get(" ")
        print("questo file si trova nella cartella core  ")
        if settings.DEBUG:
            template_name = 'index.html'
        else:
            template_name = 'index.html'
        return template_name
