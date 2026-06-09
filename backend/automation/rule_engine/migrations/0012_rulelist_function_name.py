# Generated migration: Remove FK to RuleLogic, add function_name as CharField

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rule_engine', '0011_scheduledjob_job_name_alter_scheduledjob_rule_name'),
    ]

    operations = [
        # Step 1: Add new function_name field (nullable initially)
        migrations.AddField(
            model_name='rulelist',
            name='function_name',
            field=models.CharField(default='', help_text='Reference to RuleLogic.function_name (string, not a foreign key)', max_length=255),
            preserve_default=False,
        ),
        
        # Step 2: Migrate data from rule_logic.function_name to function_name
        migrations.RunPython(
            code=lambda apps, schema_editor: migrate_function_names(apps, schema_editor),
            reverse_code=lambda apps, schema_editor: None,  # No-op on reverse
        ),
        
        # Step 3: Remove the FK to RuleLogic
        migrations.RemoveField(
            model_name='rulelist',
            name='rule_logic',
        ),
    ]


def migrate_function_names(apps, schema_editor):
    """
    Migrate function_name from related RuleLogic to the CharField.
    If the related RuleLogic is deleted, function_name stays as previously set or empty string.
    """
    RuleList = apps.get_model('rule_engine', 'RuleList')
    RuleLogic = apps.get_model('rule_engine', 'RuleLogic')
    
    for rule_list in RuleList.objects.select_related('rule_logic'):
        if rule_list.rule_logic:
            rule_list.function_name = rule_list.rule_logic.function_name
            rule_list.save(update_fields=['function_name'])
