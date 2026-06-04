from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Post, Comment, Like, Report, SavedPost
from .serializers import PostSerializer, CommentSerializer, ReportSerializer, SavedPostSerializer
from rest_framework.parsers import MultiPartParser, FormParser

class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser] 


    def get_queryset(self):
        # Only show posts that haven't been removed by an admin
        return Post.objects.filter(is_active=True)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


    # --- NEW ENDPOINT ADDED HERE ---
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_posts(self, request):
        # 1. Filter the base queryset by the currently authenticated user
        queryset = self.get_queryset().filter(author=request.user)
        
        # 2. Handle pagination (highly recommended for lists of posts)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # 3. Serialize and return the data if pagination is not configured
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    # -------------------------------

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        post = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, post=post)
        
        if not created:
            # If they already liked it, unlike it (toggle)
            like.delete()
            return Response({'status': 'unliked'})
            
        return Response({'status': 'liked'})

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        original_post = self.get_object()
        
        # Create a new post that references the original
        new_post = Post.objects.create(
            author=request.user,
            content=request.data.get('content', ''), # Optional custom text added by the user sharing it
            shared_post=original_post
        )
        return Response({'status': 'shared', 'new_post_id': new_post.id}, status=status.HTTP_201_CREATED)

class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # Filter active comments. Optionally filter by post_id if passed in URL query params: ?post=1
        queryset = Comment.objects.filter(is_active=True)
        post_id = self.request.query_params.get('post')
        if post_id:
            queryset = queryset.filter(post_id=post_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Regular users only see their own reports. Admins see all.
        if getattr(self.request.user, 'role', None) == 'admin':
            return Report.objects.all()
        return Report.objects.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class SavedPostViewSet(viewsets.ModelViewSet):
    serializer_class = SavedPostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Ensure users can only see and delete their own saved posts
        return SavedPost.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Automatically assign the logged-in user when saving a post
        serializer.save(user=self.request.user)