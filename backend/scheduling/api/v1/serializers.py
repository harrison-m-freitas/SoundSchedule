from rest_framework import serializers
from scheduling.domain.models import Service, Assignment, Member

class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ["id","name","nickname","email","phone","active","last_served_at","monthly_limit"]
        read_only_fields = ("id","name","nickname","email","phone","active","last_served_at","monthly_limit")

class AssignmentSerializer(serializers.ModelSerializer):
    member = MemberSerializer(read_only=True)
    class Meta:
        model = Assignment
        fields = ["id","status","member"]
        read_only_fields = ("id","status","member")

class ServiceSerializer(serializers.ModelSerializer):
    assignments = AssignmentSerializer(many=True, read_only=True)
    class Meta:
        model = Service
        fields = ["id","date","time","type","assignments"]
        read_only_fields = ("id","date","time","type","assignments")
