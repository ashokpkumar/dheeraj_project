from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rule_engine', '0002_rulelogic_tag_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='parammodel',
            name='param_default',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
