from rest_framework import serializers
from .models import Post, PostImage, Like, Comment, Report, SavedPost
from products.models import Product
from .models import Post

class PostImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ['id', 'image']

class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)
    author_image=serializers.ImageField(source='author.photo', read_only=True)


    class Meta:
        model = Comment
        fields = ['id', 'post', 'author', 'author_name', 'author_image', 'content', 'created_at']
        read_only_fields = ['author','author_image', 'created_at']

class PostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)
    author_location = serializers.CharField(source='author.location', read_only=True)
    images = PostImageSerializer(many=True,  required=False,read_only=True  )
    comments = CommentSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(max_length=1000000, allow_empty_file=False, use_url=False),
        write_only=True, required=False
    )
    
    # Aggregations
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    is_liked_by_me = serializers.SerializerMethodField()



    class Meta:
        model = Post
        fields = [
            'id', 'author', 'author_name', 'author_location', 'post_type', 'content', 'uploaded_images','comments',
            'linked_product', 'shared_post', 'images', 'likes_count', 
            'comments_count', 'is_liked_by_me', 'created_at'
        ]
        read_only_fields = ['author','author_name', 'author_location', 'is_active', 'created_at','comments']

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        post = Post.objects.create(**validated_data)

        for image in uploaded_images:
            PostImage.objects.create(post=post, image=image)

        return post

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_comments_count(self, obj):
        return obj.comments.filter(is_active=True).count()

    def get_is_liked_by_me(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'reporter', 'post', 'reason', 'status', 'created_at']
        read_only_fields = ['reporter', 'status', 'created_at']


class SavedPostSerializer(serializers.ModelSerializer):
    # Optional: If you want to return the full post details when listing saved posts, 
    # you can uncomment the line below. Otherwise, it will just return the post ID.
    post = PostSerializer(read_only=True) 

    class Meta:
        model = SavedPost
        fields = ['id', 'user', 'post', 'created_at']
        read_only_fields = ['user', 'created_at']

    def create(self, validated_data):
        # The user is automatically pulled from the request context in the view
        user = self.context['request'].user
        post = validated_data['post']
        
        # get_or_create prevents duplicate saves if the user spams the button
        saved_post, created = SavedPost.objects.get_or_create(user=user, post=post)
        return saved_post