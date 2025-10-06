# Initial migration for scheduling app
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Member',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('nickname', models.CharField(blank=True, max_length=60, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone', models.CharField(blank=True, max_length=30, null=True)),
                ('active', models.BooleanField(default=True)),
                ('date_joined', models.DateField(blank=True, null=True)),
                ('last_served_at', models.DateField(blank=True, null=True)),
                ('monthly_limit', models.PositiveIntegerField(default=2)),
                ('notes', models.TextField(blank=True, null=True)),
                ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='Availability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.IntegerField(help_text='0=Seg ... 6=Domingo')),
                ('shift', models.CharField(choices=[('morning', 'Manhã'), ('evening', 'Noite')], max_length=10)),
                ('active', models.BooleanField(default=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scheduling.member')),
            ],
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('time', models.TimeField()),
                ('type', models.CharField(choices=[('Culto', 'Culto'), ('Extra', 'Extra')], default='Culto', max_length=12)),
            ],
        ),
        migrations.CreateModel(
            name='ScheduleMonth',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField()),
                ('month', models.PositiveIntegerField()),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('generated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
            options={'unique_together': {('year', 'month')}},
        ),
        migrations.CreateModel(
            name='Assignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('confirmed', 'Confirmado'), ('suggested', 'Sugerido'), ('replaced', 'Substituído')], default='suggested', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='scheduling.member')),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='scheduling.service')),
            ],
            options={'unique_together': {('service', 'member')}},
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=50)),
                ('table', models.CharField(max_length=50)),
                ('record_id', models.CharField(max_length=50)),
                ('before', models.JSONField(blank=True, null=True)),
                ('after', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='availability',
            unique_together={('member', 'weekday', 'shift')},
        ),
        migrations.AlterUniqueTogether(
            name='service',
            unique_together={('date', 'time')},
        ),
    ]
