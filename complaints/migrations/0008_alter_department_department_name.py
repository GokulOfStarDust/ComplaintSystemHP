# Generated by Django 5.2.1 on 2025-06-11 10:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('complaints', '0007_alter_department_department_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='department',
            name='department_name',
            field=models.CharField(max_length=20, unique=True),
        ),
    ]
