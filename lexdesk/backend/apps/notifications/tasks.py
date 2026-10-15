from celery import shared_task

from . import reminders, services


@shared_task(ignore_result=True)
def deliver_task(delivery_id):
    services.deliver(delivery_id)


@shared_task(ignore_result=True)
def retry_deliveries():
    """Every minute: back-offs that have elapsed, texts held for quiet hours."""
    services.retry_due_deliveries()


@shared_task(ignore_result=True)
def send_due_reminders():
    """Every minute, so a "2 hours before" reminder is not 59 minutes late."""
    reminders.send_due_reminders()


@shared_task(ignore_result=True)
def send_daily_agendas():
    reminders.send_daily_agendas()
