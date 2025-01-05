# Generated by Django 2.1.4 on 2019-01-05 16:09

from django.db import migrations, models
import prose.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("content", prose.fields.DocumentContentField()),
            ],
        ),
    ]