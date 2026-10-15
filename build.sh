#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
if [ -f full_backup.json ]; then
  python manage.py loaddata full_backup.json
fi
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); user, _ = User.objects.get_or_create(username='admin', defaults={'role': 'admin', 'is_superuser': True, 'is_staff': True}); user.role = 'admin'; user.is_superuser = True; user.is_staff = True; user.save()"
