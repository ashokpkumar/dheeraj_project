from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rule_engine', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='rulelogic',
            name='tag',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='rulelogic',
            name='color',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
