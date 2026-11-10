import redis
from actions.utils import create_action
from common.decorators import ajax_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from .fetch import ImageFetchError
from .forms import ImageCreateForm, ImageUploadForm
from .models import Image
from core.redis_client import get_redis
import logging

logger = logging.getLogger(__name__)


@login_required
def image_create(request):
    if request.method == 'POST':
        # form is sent
        form = ImageCreateForm(data=request.POST)
        if form.is_valid():
            # form data is valid
            try:
                new_item = form.save(commit=False)
            except ImageFetchError as e:
                form.add_error('url', str(e))
            else:
                # assign current user to the item
                new_item.user = request.user
                new_item.save()
                create_action(request.user, 'shared image', new_item)
                messages.success(request, 'Image added successfully')
                # redirect to new created item detail view
                return redirect(new_item.get_absolute_url())
    else:
        # build form with data provided by the bookmarklet via GET
        form = ImageCreateForm(data=request.GET)
    return render(request,
                  'images/image/create.html',
                  {'section': 'images',
                   'form': form})


@login_required
def image_detail(request, id, slug):
    image = get_object_or_404(Image, id=id, slug=slug)
    # increment total image views by 1
    total_views = 0
    r = get_redis()
    if r is not None:
        try:
            total_views = r.incr(f'image:{image.id}:views')
            # increment image ranking by 1
            r.zincrby('image_ranking', 1, image.id)
        except redis.RedisError as e:
            logger.error(f"Redis error in image_detail: {e}")
    return render(request,
                  'images/image/detail.html',
                  {'section': 'images',
                   'image': image,
                   'total_views': total_views})


@ajax_required
@login_required
@require_POST
def image_like(request):
    image_id = request.POST.get('id')
    action = request.POST.get('action')
    if image_id and action:
        try:
            image = Image.objects.get(id=image_id)
            if action == 'like':
                image.users_like.add(request.user)
                create_action(request.user, 'likes', image)
            else:
                image.users_like.remove(request.user)
            return JsonResponse({'status': 'ok'})
        except:
            pass
    return JsonResponse({'status': 'error'})


def image_list(request):
    # '-id' breaks total_likes ties so paginated pages don't overlap.
    most_likes = Image.objects.order_by('-total_likes', '-id')
    if not request.user.is_authenticated:
        # Logged-out visitors only see staff uploads; members posted theirs
        # under login-only visibility.
        most_likes = most_likes.filter(user__is_active=True,
                                       user__is_staff=True)
    paginator = Paginator(most_likes, 9)
    page = request.GET.get('page')
    try:
        most_likes = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer deliver the first page
        most_likes = paginator.page(1)
    except EmptyPage:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # If the request is AJAX and the page is out of range
            # return an empty page
            return HttpResponse('')
        # If page is out of range deliver last page of results
        most_likes = paginator.page(paginator.num_pages)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request,
                      'images/image/list_ajax.html',
                      {'section': 'images', 'most_liked': most_likes})
    most_viewed = []
    r = get_redis() if request.user.is_authenticated else None
    if r is not None:
        try:
            image_ranking = r.zrange('image_ranking', 0, -1, desc=True)[:5]
        except redis.RedisError as e:
            logger.error(f"Redis error in image_list: {e}")
            image_ranking = []
        image_ranking_ids = [int(id) for id in image_ranking]
        # get most viewed images
        most_viewed = list(Image.objects.filter(
            id__in=image_ranking_ids))
        most_viewed.sort(key=lambda x: image_ranking_ids.index(x.id))
    return render(request,
                  'images/image/list.html',
                  {
                      'section': 'images',
                      'most_liked': most_likes,
                      'most_viewed': most_viewed}
                  )


@login_required
def image_ranking(request):
    # get image ranking dictionary
    r = get_redis()
    image_ranking = r.zrange('image_ranking', 0, -1,
                             desc=True)[:10]
    image_ranking_ids = [int(id) for id in image_ranking]
    # get most viewed images
    most_viewed = list(Image.objects.filter(
        id__in=image_ranking_ids))
    most_viewed.sort(key=lambda x: image_ranking_ids.index(x.id))
    return render(request,
                  'images/image/ranking.html',
                  {'section': 'images',
                   'most_viewed': most_viewed})


@login_required
def image_upload(request):
    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                new_item = form.save(commit=False)
            except ImageFetchError as e:
                form.add_error('url', str(e))
            else:
                new_item.user = request.user
                new_item.save()
                create_action(request.user, 'uploaded image', new_item)
                messages.success(request, 'Image uploaded successfully')
                return redirect(new_item.get_absolute_url())
    else:
        form = ImageUploadForm()
    return render(request,
                  'images/image/upload.html',
                  {'section': 'images',
                   'form': form})
