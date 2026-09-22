from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0007_csvprocesstask_current_step_csvprocesstask_message_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="verification",
            field=models.BooleanField(
                default=True,
                help_text="Whether to verify generated email candidates with MailTester",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="combinations_path",
            field=models.CharField(
                blank=True,
                help_text="Local file path or Supabase Storage key for email combinations",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="combinations_url",
            field=models.URLField(
                blank=True,
                help_text="Supabase storage direct / signed download URL for email combinations",
                max_length=1000,
            ),
        ),
    ]
