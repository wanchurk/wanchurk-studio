from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="supportconversation",
            name="revision",
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
    ]