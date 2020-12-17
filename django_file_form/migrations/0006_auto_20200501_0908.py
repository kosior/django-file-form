# Generated by Django 3.0.5 on 2020-05-01 14:08

from django.db import migrations, models
import django_file_form.models

from . import storage


class Migration(migrations.Migration):

    dependencies = [
        ("django_file_form", "0005_auto_20200407_0814"),
    ]

    operations = [
        migrations.AlterField(
            model_name="uploadedfile",
            name="uploaded_file",
            field=models.FileField(
                max_length=255,
                storage=storage,
                upload_to=django_file_form.models.get_upload_to,
            ),
        ),
    ]