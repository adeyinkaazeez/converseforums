from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from typing import Any
from django.db import models
from django.db.models.query import QuerySet
from .models import Cultures_Comment, Cultures
from .forms import EmailPostForm, CommentForm, PostForm
from taggit.models import Tag
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
from django.core.mail import send_mail
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.text import slugify
from actions.utils import create_action
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import HttpResponseRedirect
from django.views import View
from hitcount.models import HitCount
from hitcount.views import HitCountMixin
from hitcount.utils import get_hitcount_model
from notify.signals import notify
#import redis
from django.conf import settings


#r = redis.Redis(host=settings.REDIS_HOST,
#                port=settings.REDIS_PORT,
#                db=settings.REDIS_DB)


# Create your views here.

def Create_Post(request):
    if request.method == 'POST':
       form = PostForm(request.POST or None, request.FILES)
       if form.is_valid():
          post = form.save(commit=False)
          post.author = request.user
          post.slug= slugify(post.title)
          post.save()
          form.save_m2m() 
          create_action(request.user, 'created a post', post) 
          messages.success(request, 'Congrats! Your Post was submitted as draft. Undergoing review for approval.....')
          return redirect('cultures:create_post')
    else:
       form = PostForm(request.POST or None)
    return render(request, 'culture_post/create_post.html',
                  {'form':form})

def post_list(request, tag_slug=None):
     cultural_posts = all_Cultural_Posts(request) 
     #tags
     tag = None
     if tag_slug:
      tag = get_object_or_404(Tag, slug=tag_slug)
      post_list = post_list.filter(tags__in=[tag])
      
     context = { 
         "cultural_posts":cultural_posts,
          'tag': tag
     }   
     return render(request,'culture_post/culture_home.html', context)

def list_load_cultural_posts_view(request):
   cultural_posts = all_Cultural_Posts(request)
   context = {'cultural_posts':cultural_posts}
   return render(request, "culture_post/partials/culture_post_list.html", context)

def all_Cultural_Posts(request):
   objs = Cultures.published.select_related('author').all()
   page_number = request.GET.get('page', 15)
   paginator = Paginator(objs, per_page=1)
   page_objects_home = paginator.get_page(page_number)
   return page_objects_home

def like_post(request, pk):
   post = Cultures.objects.get(pk=pk)
   if request.method =='POST':
      if not post.likes.filter(id=request.user.pk).exists():
         post.likes.add( request.user)
         post.save()
         create_action(request.user, 'endorsed', post)
         return render(request, 'culture_post/partials/like.html', context={'post':post})
      else:
         post.likes.remove(request.user)
         post.save()
         create_action(request.user, 'neutral', post)
         return render(request, 'culture_post/partials/like.html', context={'post':post})

@login_required
def Update_Post(request, pk=None):
   post = Cultures.objects.get(pk=pk)
   post.edited = False
   if request.method == 'POST':
      form = PostForm(request.POST, request.FILES,  instance=post)
      if form.is_valid():
         post.edited = True
         form.save()
         create_action(request.user, 'Updated', post)
         return render(request,  'culture_post/addInForum.html', {'post':post})
   else:
      form = PostForm(instance=post)
   return render(request, 'culture_post/addInForum.html', {'form':form, 'post':post})



#deleting post
def delete_post(request, pk=None):
   post = Cultures.objects.get(pk=pk).delete()
   create_action(request.user, 'removed', post)
   return render(request, 'culture_post/delete.html')


def post_detail(request, year, month, day,post):    
    post = get_object_or_404(Cultures,                                                          
                             status=Cultures.Status.PUBLISHED,
                              slug=post,
                              publish__year=year,                             
                              publish__month=month,                            
                            publish__day=day) 
     # List of active comments for this post    
    comments = post.culture_comments.filter(active=True)  

    #let's paginate our comment to 20 comments per post
    paginator= Paginator(comments, 20) #20 posts per page
    page_number= request.GET.get('page', 1)
     
    try:
       all_comments= paginator.page(page_number)
    except PageNotAnInteger:
       all_comments= paginator.page(1)
    except EmptyPage:
       all_comments = paginator.page(paginator.num_pages)
 
    # Form for users to comment    
    form = CommentForm()  

    post_tags_ids = post.tags.values_list('id', flat=True)
    similar_posts = Cultures.published.filter(tags__in=post_tags_ids)\
                                            .exclude(id=post.id)

    similar_posts = similar_posts.annotate(same_tags=Count('tags'))\
                                           .order_by('-same_tags','-publish')[:4]  
    
    
    most_viewed = Cultures.objects.filter(status=Cultures.Status.PUBLISHED).order_by( 'hit_count_generic')[:5]        

    context = {'post': post,
               'comments' : comments,
               'form' : form,
               'similar_posts':similar_posts,
               'most_viewed':most_viewed,
               'all_comments':all_comments,}
    
    #hitcount logic
    hit_count = get_hitcount_model().objects.get_for_object(post)
    hits = hit_count.hits
    hitContext = context['hitcount'] = {'pk':hit_count.pk}
    hit_count_response = HitCountMixin.hit_count(request, hit_count)
    if hit_count_response.hit_counted:
       hits = hits + 1
       hitContext['hit_counted'] = hit_count_response.hit_counted
       hitContext['hit_message'] = hit_count_response.hit_message
       hitContext['total_hits'] = hits   

    return render(request, 'culture_post/culture_details.html', context)


def post_share(request, post_id):    
   # Retrieve post by id    
   post = get_object_or_404(Cultures, id=post_id, status=Cultures.Status.PUBLISHED)

   sent = False
     
   if request.method == 'POST':        
      # Form was submitted        
      form = EmailPostForm(request.POST)        
      if form.is_valid():            
         # Form fields passed validation            
         cd = form.cleaned_data 
         post_url = request.build_absolute_uri(post.get_absolute_url())
         subject = f"{cd['name']} recommends you read "  f"{post.title}"            
         message = f"Read {post.title} at {post_url}\n\n"  f"{cd['name']}\'s comments: {cd['comments']}"            
         send_mail(subject, message, 'your_account@gmail.com',                      
                   [cd['to']])            
         sent = True           
         # ... send email    
   else:        
    form = EmailPostForm()    
   return render(request, 'culture_comment/share.html', 
                 {'post': post,
                  'form': form,  
                  'sent': sent})


@login_required
def post_comment(request, post_id):    
  post = get_object_or_404(Cultures, id=post_id, status=Cultures.Status.PUBLISHED)    
  comment = None

  if request.method=='POST':    
     # A comment was posted    
     form = CommentForm(request.POST, request.FILES)
     if form.is_valid():        
        # Create a Comment object without saving it to the database        
        comment = form.save(commit=False)        
        # Assign the post to the comment        
        comment.post = post  
        comment.name = request.user      
        # Save the comment to the database        
        comment.save()
        create_action(request.user, 'commented on', post)  

  else:
     form = CommentForm()
  return render(request , 'culture_comment/comment_confirm.html',                           
                {'post': post,                            
                 'form': form,                            
                 'comment': comment})


def Update_Comment(request, pk=None):
   comment = Cultures_Comment.objects.get(pk=pk)
   comment.edited = False
   if request.method == 'POST':
      
      form = CommentForm(request.POST, request.FILES, instance=comment)
      if form.is_valid():
         comment.edited = True
         form.save()
         messages.success(request, 'Your Comment Updated Successuflly')
         return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
   else:
      form = CommentForm(instance=comment)

   return render(request, 'culture_comment/comment_edit_form.html',
                   { 'form':form,
                   'comment':comment,
 })

#deleting post
def delete_comment(request, pk=None):
   comment = Cultures_Comment.objects.get(pk=pk).delete()
   create_action(request.user, 'removed ', comment)
   return render(request, 'culture_comment/delete.html')

# handling reply, reply view
def reply_page(request):
    if request.method == "POST":

        form = CommentForm(request.POST, request.FILES)

        if form.is_valid():
            post_id = request.POST.get('post_id')  # from hidden input
            parent_id = request.POST.get('parent')  # from hidden input
            post_url = request.POST.get('post_url')  # from hidden input

            reply = form.save(commit=False)
                
    
            reply.post = Cultures(id=post_id)
            reply.culture_parent = Cultures_Comment(id=parent_id)
            comment = Cultures_Comment.objects.get(id=parent_id)
             # Assign reply to the login user
            reply.name = request.user
            reply.save()
            messages.success(request, 'Reply Successfully Submitted ')
            #sending notification to the owner of original comment that someone has replied to the comment
            notify.send(request.user, recipient=comment.name, actor=request.user, verb='replied to your comment',
                target= reply.post, nf_type = 'followed_by_one_user')
            return redirect(post_url+'#'+str(reply.id))

    return redirect("/")


class Like_comment(LoginRequiredMixin, View):
   def post(self, request, post_pk=None, pk=None, *args, **kwargs):
      post = Cultures.objects.get(pk=post_pk)
      comment = Cultures_Comment.objects.get(pk=pk)
      author = comment.name
      if request.method=="POST":
          is_dislike = False
          for dislike in comment.dislikes.all():
            if dislike ==request.user:
                is_dislike = True
                break
          if is_dislike:
             comment.dislikes.remove(request.user)
             
        

          is_like = False
          for like in comment.likes.all():
            if like == request.user:
               is_like = True
               break
          if not is_like:
             comment.likes.add(request.user)
             create_action(request.user, 'likes the',  comment)
             notify.send(request.user, recipient=author, actor=request.user, verb='likes your comment  ',
                target= post, nf_type = 'followed_by_one_user')
             return render(request,'culture_comment/partials/like.html', context={'comment':comment, 'post':post})
          if is_like:
             comment.likes.remove(request.user)
             create_action(request.user, 'is now neutral on', comment)
             return render(request,'culture_comment/partials/like.html', context={'comment':comment, 'post':post})






